"""Tests for the verification pass: real source evidence and the verify model.

The verifier must judge actual code (±N lines around the finding), not a prose
description, and must be able to run on a separately configured model. Neither
behaviour may be hard-coded.
"""

import json

import pytest

from agentguard.analysis.tools import ReadFileContextTool, default_registry
from agentguard.analysis.tools.read_file import extract_line_window
from agentguard.core.policy import AgentPolicy
from agentguard.core.schemas import AgentState, Decision, Finding, RiskLevel
from pr_agent.agent_exec.nodes import verify_node
from pr_agent.algo.types import EDIT_TYPE, FilePatchInfo


def _file_with_source(source: str, filename: str = "a.py") -> FilePatchInfo:
    """A FilePatchInfo whose head_file holds real file content (as providers do)."""
    return FilePatchInfo(
        base_file=source,
        head_file=source,
        patch="@@ -1,1 +1,1 @@\n-x = 1\n+x = 2\n",
        filename=filename,
        edit_type=EDIT_TYPE.MODIFIED,
        language="python",
    )


class _ScriptedLLM:
    """Minimal AgentLLM stand-in recording the model name and prompts."""

    def __init__(self, model: str, response: str) -> None:
        self._model = model
        self._response = response
        self.prompts = []

    def model_name(self) -> str:
        return self._model

    async def complete(self, system: str, user: str, temperature: float = 0.2):
        self.prompts.append(user)
        return self._response, "stop"


def test_extract_line_window_uses_full_head_file_content():
    lines = "\n".join(f"line_{i} = {i}" for i in range(1, 101))
    window = extract_line_window(_file_with_source(lines), 50, 30)
    assert window["source"] == "head_file"
    assert window["lines"][0]["line"] == 20
    assert window["lines"][-1]["line"] == 80
    assert [entry["line"] for entry in window["lines"] if entry["is_target"]] == [50]


def test_extract_line_window_falls_back_to_patch_hunks():
    # Jev test files store the bare filename in head_file; the window must then
    # be reconstructed from the unified diff instead of trusting that string.
    patch = "@@ -10,3 +10,4 @@\n context\n+added line\n context2\n context3\n"
    file_patch = FilePatchInfo(
        base_file="a.py",
        head_file="a.py",
        patch=patch,
        filename="a.py",
        edit_type=EDIT_TYPE.MODIFIED,
        language="python",
    )
    window = extract_line_window(file_patch, 11, 30)
    assert window["source"] == "patch"
    assert [entry["text"] for entry in window["lines"]][:3] == ["context", "added line", "context2"]


@pytest.mark.asyncio
async def test_read_file_context_returns_window_around_line():
    source = "\n".join(f"row_{i}" for i in range(1, 60))
    tool = ReadFileContextTool([_file_with_source(source)])
    result = await tool.execute({"file_path": "a.py", "line_number": 30, "context_lines": 30})
    assert result.success is True
    assert result.data["context"][0]["lines"][0]["line"] == 1
    assert any(entry["is_target"] for entry in result.data["context"][0]["lines"])


@pytest.mark.asyncio
async def test_verify_node_sends_real_source_context_and_uses_verify_model():
    source = "\n".join(f"code_line_{i}" for i in range(1, 80))
    file_patch = _file_with_source(source)
    registry = default_registry(ReadFileContextTool([file_patch]))
    finding = Finding(
        id="f1",
        file_path="a.py",
        line_number=40,
        title="use of os.system",
        description="shell injection",
        risk_level=RiskLevel.HIGH,
        confidence=0.4,
    )
    state = AgentState(
        messages=[],
        findings=[finding],
        decision=Decision(action="verify", finding_id="f1"),
        step=3,
    )

    llm = _ScriptedLLM("verify-model", json.dumps({"verified": True, "note": "confirmed"}))
    policy = AgentPolicy(verify_model="verify-model", verify_context_lines=30)
    update = await verify_node(state, llm, registry, policy)

    prompt = llm.prompts[0]
    assert "SOURCE CONTEXT" in prompt
    assert "code_line_10" in prompt and "code_line_70" in prompt
    assert "code_line_9\n" not in prompt  # outside the ±30 window
    assert llm.model_name() == "verify-model"
    assert update["findings"][0].verified is True
    assert update["findings"][0].verification_note == "confirmed"
    # Evidence gathering is audited like any other tool execution.
    assert update["audit_events"][-1].tool_name == "read_file_context"
    assert "verify-model" in update["trajectory"][-1].summary


@pytest.mark.asyncio
async def test_verify_node_survives_missing_evidence_tool():
    finding = Finding(id="f1", file_path="a.py", line_number=3, title="t")
    state = AgentState(findings=[finding], decision=Decision(action="verify", finding_id="f1"))
    llm = _ScriptedLLM("verify-model", json.dumps({"verified": False, "note": "no code shown"}))
    update = await verify_node(state, llm, registry=None, policy=AgentPolicy())
    assert "source context unavailable" in llm.prompts[0]
    assert update["findings"][0].verified is False


def test_policy_reads_configured_review_and_verify_models():
    """Both passes are model-selectable from configuration, never hard-coded."""
    from agentguard.core.policy import load_policy
    from pr_agent.config_loader import get_settings

    settings = get_settings()
    agent_exec = settings.get("agent_exec", {}) or {}
    previous_review = agent_exec.get("review_model", "")
    previous_verify = agent_exec.get("verify_model", "")
    settings.set("agent_exec.review_model", "deepseek-v4-flash")
    settings.set("agent_exec.verify_model", "deepseek-v4-pro")
    try:
        policy = load_policy()
        assert policy.review_model == "deepseek-v4-flash"
        assert policy.verify_model == "deepseek-v4-pro"
    finally:
        settings.set("agent_exec.review_model", previous_review)
        settings.set("agent_exec.verify_model", previous_verify)


def test_agent_llm_falls_back_and_clones_with_model():
    from agentguard.core.llm import AgentLLM

    handler = object()
    base = AgentLLM(model="deepseek-v4-flash", handler=handler)
    assert base.model_name() == "deepseek-v4-flash"
    assert base.with_model("deepseek-v4-pro").model_name() == "deepseek-v4-pro"
    # No distinct model configured: the same instance is reused (one client).
    assert base.with_model("") is base
    assert base.with_model("deepseek-v4-flash") is base
