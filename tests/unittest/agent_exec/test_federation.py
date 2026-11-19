"""Tests for multi-subagent fan-out and merge (agentguard.orchestration.federation)."""

import asyncio
import json

import pytest

from agentguard.core.policy import FederationPolicy
from agentguard.core.schemas import Finding, RiskLevel, ToolResult, ToolStatus
from agentguard.orchestration.federation import (
    BudgetedAgentLLM,
    FederationBudget,
    ReviewerFederation,
    evaluate_federation,
    merge_findings,
    partition_files,
    review_with_audit,
    should_use_federation,
)
from pr_agent.algo.types import EDIT_TYPE, FilePatchInfo


def _py_file(name: str, patch: str) -> FilePatchInfo:
    return FilePatchInfo(
        base_file=name,
        head_file=name,
        patch=patch,
        filename=name,
        edit_type=EDIT_TYPE.MODIFIED,
        language="python",
    )


def _finding(id, file, line, title, risk="medium", confidence=0.8, verified=None, note=None):
    return Finding(
        id=id,
        file_path=file,
        line_number=line,
        title=title,
        risk_level=RiskLevel(risk),
        confidence=confidence,
        verified=verified,
        verification_note=note,
    )


def test_partition_files_one_per_batch_by_default():
    files = [_py_file(f"f{i}.py", "+x\n") for i in range(3)]
    batches = partition_files(files)
    assert [len(b) for b in batches] == [1, 1, 1]


def test_partition_files_respects_max_files_per_batch():
    files = [_py_file(f"f{i}.py", "+x\n") for i in range(5)]
    batches = partition_files(files, max_files_per_batch=2)
    assert [len(b) for b in batches] == [2, 2, 1]


def test_partition_files_empty_input():
    assert partition_files([]) == []


def test_merge_findings_dedups_same_location_and_title():
    a = _finding("f1", "a.py", 3, "use of eval", risk="medium", confidence=0.5)
    b = _finding("f2", "a.py", 3, "use of eval", risk="medium", confidence=0.5)
    merged = merge_findings([[a], [b]])
    # Same file+title+line+risk: the duplicate is dropped, keeping the first.
    assert len(merged) == 1
    assert merged[0].id == "f1"


def test_merge_findings_dedups_differently_worded_titles_within_line_window():
    # Two sub-agents describe the same defect with different wording; an exact
    # title match would miss this, the line window plus contained title catches it.
    a = _finding("f1", "a.py", 10, "use of eval", risk="high")
    b = _finding("f2", "a.py", 12, "use of eval on user input", risk="high")
    merged = merge_findings([[a], [b]])
    assert len(merged) == 1


def test_merge_findings_dedups_chinese_titles_without_exact_match():
    a = _finding("f1", "a.py", 10, "空指针风险", risk="high")
    b = _finding("f2", "a.py", 11, "空指针风险：未校验返回值", risk="high")
    merged = merge_findings([[a], [b]])
    assert len(merged) == 1


def test_merge_findings_keeps_same_title_beyond_line_window():
    a = _finding("f1", "a.py", 10, "use of eval", risk="high")
    b = _finding("f2", "a.py", 40, "use of eval", risk="high")
    merged = merge_findings([[a], [b]])
    assert len(merged) == 2


def test_merge_findings_keeps_different_risk_levels_separate():
    a = _finding("f1", "a.py", 10, "use of eval", risk="medium")
    b = _finding("f2", "a.py", 10, "use of eval", risk="critical")
    merged = merge_findings([[a], [b]])
    assert len(merged) == 2


def test_merge_findings_respects_configured_line_window():
    a = _finding("f1", "a.py", 10, "use of eval", risk="high")
    b = _finding("f2", "a.py", 14, "use of eval", risk="high")
    assert len(merge_findings([[a], [b]], FederationPolicy(dedup_line_window=5))) == 1
    assert len(merge_findings([[a], [b]], FederationPolicy(dedup_line_window=2))) == 2


def test_merge_findings_migrates_verified_verdict_and_richer_description():
    a = _finding("f1", "a.py", 10, "use of eval", risk="high")
    b = _finding("f2", "a.py", 10, "use of eval on user input", risk="high", verified=True, note="ok")
    merged = merge_findings([[a], [b]])
    assert len(merged) == 1
    assert merged[0].verified is True
    assert merged[0].verification_note == "ok"


def test_merge_findings_keeps_different_locations_separately():
    a = _finding("f1", "a.py", 3, "issue A")
    b = _finding("f2", "b.py", 5, "issue B")
    merged = merge_findings([[a], [b]])
    assert {f.id for f in merged} == {"f1", "f2"}


def test_merge_findings_carries_verification_verdict_from_later_batch():
    a = _finding("f1", "a.py", 3, "command injection", risk="high", confidence=0.3, verified=None)
    b = _finding("f2", "a.py", 3, "command injection", risk="high", confidence=0.3, verified=True, note="confirmed")
    merged = merge_findings([[a], [b]])
    # The first is kept but the verification verdict from the second is carried.
    assert len(merged) == 1
    assert merged[0].verified is True
    assert merged[0].verification_note == "confirmed"


def test_merge_findings_is_deterministic_order():
    a = _finding("f1", "a.py", 1, "x")
    b = _finding("f2", "a.py", 2, "y")
    out1 = merge_findings([[a], [b]])
    out2 = merge_findings([[a], [b]])
    assert [f.id for f in out1] == [f.id for f in out2] == ["f1", "f2"]


class _StubState:
    """Minimal stand-in for AgentState exposing the fields the merger reads."""

    def __init__(self, findings):
        self.findings = findings
        self.audit_events = []
        self.trajectory = []
        self.tool_results = [
            ToolResult(tool_name="read_file_context", success=True, status=ToolStatus.COMPLETED, data={})
        ]


class _StubRunner:
    """Returns a scripted state per batch; records the batches it received."""

    def __init__(self, findings_by_file):
        self._findings_by_file = findings_by_file
        self.batches = []

    async def run(self, batch):
        self.batches.append(batch)
        # Return findings keyed by the first file name in the batch.
        key = batch[0].filename if batch else ""
        return _StubState(list(self._findings_by_file.get(key, [])))


@pytest.mark.asyncio
async def test_federation_runs_one_subagent_per_file_and_merges():
    files = [_py_file("a.py", "+x\n"), _py_file("b.py", "+y\n")]
    findings_by_file = {
        "a.py": [_finding("a1", "a.py", 1, "issue A")],
        "b.py": [_finding("b1", "b.py", 2, "issue B")],
    }
    stub_runner = _StubRunner(findings_by_file)
    fed = ReviewerFederation(runner_factory=lambda: stub_runner)

    findings = await fed.review(files)

    # Two sub-agents ran, one per file, and the merger combined their findings.
    assert len(stub_runner.batches) == 2
    assert {f.id for f in findings} == {"a1", "b1"}


@pytest.mark.asyncio
async def test_federation_dedups_across_subagents():
    files = [_py_file("a.py", "+x\n"), _py_file("b.py", "+y\n")]
    # Both sub-agents report the exact same location+title -> merged to one.
    findings_by_file = {
        "a.py": [_finding("a1", "shared.py", 3, "dup issue")],
        "b.py": [_finding("b1", "shared.py", 3, "dup issue")],
    }
    stub_runner = _StubRunner(findings_by_file)
    fed = ReviewerFederation(runner_factory=lambda: stub_runner)

    findings = await fed.review(files)

    assert len(findings) == 1


@pytest.mark.asyncio
async def test_federation_empty_diff_returns_empty():
    fed = ReviewerFederation(runner_factory=lambda: _StubRunner({}))
    assert await fed.review([]) == []


@pytest.mark.asyncio
async def test_review_with_audit_aggregates_across_subagents():
    files = [_py_file("a.py", "+x\n"), _py_file("b.py", "+y\n")]
    findings_by_file = {
        "a.py": [_finding("a1", "a.py", 1, "issue A")],
        "b.py": [_finding("b1", "b.py", 2, "issue B")],
    }
    stub_runner = _StubRunner(findings_by_file)

    findings, audits, trajectories, tool_results = await review_with_audit(
        files, runner_factory=lambda: stub_runner
    )

    assert {f.id for f in findings} == {"a1", "b1"}
    # One audit per sub-agent (empty in stub) + one tool result per sub-agent.
    assert len(tool_results) == 2


class _FlakyRunner:
    """Raises for one designated file; returns one finding for every other."""

    def __init__(self, bad_file: str):
        self._bad_file = bad_file
        self.batches = []

    async def run(self, batch):
        self.batches.append(batch)
        if batch[0].filename == self._bad_file:
            raise RuntimeError("boom")
        name = batch[0].filename
        return _StubState([_finding(name.replace(".py", "1"), name, 1, "issue")])


@pytest.mark.asyncio
async def test_federation_failure_isolation_skips_broken_batch():
    files = [_py_file("a.py", "+x\n"), _py_file("bad.py", "+x\n"), _py_file("c.py", "+x\n")]
    fed = ReviewerFederation(
        runner_factory=lambda: _FlakyRunner("bad.py"),
        policy=FederationPolicy(enabled=True, max_concurrency=2),
    )

    findings = await fed.review(files)

    # The broken sub-agent is skipped; the healthy ones still contribute.
    assert len(findings) == 2
    assert {f.id for f in findings} == {"a1", "c1"}


@pytest.mark.asyncio
async def test_federation_caps_concurrent_subagents():
    in_flight = 0
    peak = 0

    class _SlowRunner:
        async def run(self, batch):
            nonlocal in_flight, peak
            in_flight += 1
            peak = max(peak, in_flight)
            await asyncio.sleep(0.01)
            in_flight -= 1
            return _StubState([])

    fed = ReviewerFederation(
        runner_factory=_SlowRunner,
        policy=FederationPolicy(enabled=True, max_concurrency=1),
    )
    files = [_py_file(f"f{i}.py", "+x\n") for i in range(4)]

    await fed.review(files)

    # The semaphore serialized the sub-agents despite concurrent gather.
    assert peak == 1


def test_should_use_federation_gate():
    enabled = FederationPolicy(enabled=True, min_files=4)
    assert should_use_federation(3, enabled) is False
    assert should_use_federation(4, enabled) is True
    assert should_use_federation(20, FederationPolicy(enabled=False, min_files=4)) is False


def test_evaluate_federation_fans_out_on_file_count():
    policy = FederationPolicy(enabled=True, min_files=4, min_diff_tokens=100000)
    files = [_py_file(f"f{i}.py", "+x\n") for i in range(4)]

    decision = evaluate_federation(files, policy)

    assert decision.use_federation is True
    assert decision.num_files == 4
    assert any("files=4" in r for r in decision.reasons)


def test_evaluate_federation_fans_out_on_single_huge_file():
    # One file only, but a huge patch: token estimate crosses the threshold.
    policy = FederationPolicy(enabled=True, min_files=4, min_diff_tokens=100)
    big_patch = "+" + "x" * 1000  # ~250 estimated tokens
    files = [_py_file("huge.py", big_patch)]

    decision = evaluate_federation(files, policy)

    assert decision.use_federation is True
    assert decision.num_files == 1
    assert decision.estimated_tokens >= 100
    assert any("estimated_diff_tokens" in r for r in decision.reasons)


def test_evaluate_federation_disabled_reports_reason():
    policy = FederationPolicy(enabled=False, min_files=1)
    decision = evaluate_federation([_py_file("a.py", "+x\n")], policy)

    assert decision.use_federation is False
    assert any("federation_enabled=false" in r for r in decision.reasons)


def test_evaluate_federation_small_pr_stays_single():
    policy = FederationPolicy(enabled=True, min_files=4, min_diff_tokens=100000)
    decision = evaluate_federation([_py_file("a.py", "+x\n")], policy)

    assert decision.use_federation is False
    assert any("files=1" in r for r in decision.reasons)


class _FakeHandler:
    """Records chat_completion calls; returns a fixed body."""

    def __init__(self):
        self.calls = 0

    async def chat_completion(self, **kwargs):
        self.calls += 1
        return "real model response", "stop"


@pytest.mark.asyncio
async def test_budgeted_llm_degrades_to_canned_finalize_when_exhausted():
    handler = _FakeHandler()
    llm = BudgetedAgentLLM(FederationBudget(max_calls=1), ai_handler_factory=lambda: handler)

    first, _ = await llm.complete(system="s", user="u")
    second, _ = await llm.complete(system="s", user="u")

    # Exactly one real call; the rest degrade to a valid finalize decision.
    assert handler.calls == 1
    assert first == "real model response"
    payload = json.loads(second)
    assert payload["action"] == "finalize"
    assert "budget" in payload["reasoning"]


def test_federation_budget_try_consume():
    budget = FederationBudget(max_calls=2)
    assert budget.try_consume() is True
    assert budget.try_consume() is True
    assert budget.try_consume() is False
    assert budget.used == 2
