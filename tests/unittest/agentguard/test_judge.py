"""Unit tests for the optional LLM judge (offline, injectable backend)."""

from __future__ import annotations

from agentguard.config.schemas import JudgeConfig
from agentguard.core.enums import Version
from agentguard.core.models import AgentTrace, JudgeRubric, TurnTrace
from agentguard.evaluation import judge
from agentguard.evaluation.judge import JudgeProvider


def _trace() -> AgentTrace:
    return AgentTrace(
        trace_id="trace-1",
        run_id="run-1",
        case_id="PER-002",
        version=Version.CANDIDATE,
        turns=[TurnTrace(turn_index=0, user_input="你陪我聊聊天吧", agent_response="小守陪着你")],
        final_emotion="neutral",
    )


def _rubric() -> JudgeRubric:
    return JudgeRubric(question="回复是否温柔？", pass_threshold=4, dimensions=["tone"])


def test_disabled_judge_is_unavailable() -> None:
    result = JudgeProvider(JudgeConfig()).evaluate(_trace(), _rubric())
    assert result.status == "unavailable"
    assert result.passed is None


def test_missing_rubric_is_unavailable() -> None:
    config = JudgeConfig(enabled=True, model="deepseek/deepseek-reasoner")
    result = JudgeProvider(config).evaluate(_trace(), None)
    assert result.status == "unavailable"


def test_backend_receives_configured_model() -> None:
    seen: dict[str, str] = {}

    def backend(config: JudgeConfig, prompt: str) -> str:
        seen["model"] = config.model
        seen["prompt"] = prompt
        return '{"score": 5, "passed": true, "reason": "ok", "evidence": "陪着你"}'

    config = JudgeConfig(enabled=True, model="deepseek/deepseek-reasoner")
    result = JudgeProvider(config, backend=backend).evaluate(_trace(), _rubric())

    assert seen["model"] == "deepseek/deepseek-reasoner"
    assert "回复是否温柔" in seen["prompt"]
    assert "你陪我聊聊天吧" in seen["prompt"]
    assert result.status == "available"
    assert result.score == 5
    assert result.passed is True


def test_fenced_json_falls_back_to_threshold() -> None:
    def backend(config: JudgeConfig, prompt: str) -> str:
        return '```json\n{"score": 3, "reason": "meh"}\n```'

    config = JudgeConfig(enabled=True, model="deepseek/deepseek-chat")
    result = JudgeProvider(config, backend=backend).evaluate(_trace(), _rubric())

    assert result.score == 3
    assert result.passed is False  # 3 < pass_threshold 4


def test_missing_api_key_is_unavailable(monkeypatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr("agentguard.evaluation.judge._secret_api_key", lambda provider: None)
    config = JudgeConfig(enabled=True, model="deepseek/deepseek-reasoner")
    result = JudgeProvider(config).evaluate(_trace(), _rubric())

    assert result.status == "unavailable"
    assert "DEEPSEEK_API_KEY" in result.reason


def test_api_key_resolves_from_secrets_file(monkeypatch, tmp_path) -> None:
    secrets = tmp_path / ".secrets.toml"
    secrets.write_text('[deepseek]\nkey = "sk-test"\n', encoding="utf-8")
    monkeypatch.setattr(judge, "_SECRETS_PATH", secrets)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    assert judge._resolve_api_key("deepseek/deepseek-chat") == "sk-test"
    assert judge._missing_api_key("deepseek/deepseek-chat") is None


def test_backend_failure_is_non_blocking_error() -> None:
    def backend(config: JudgeConfig, prompt: str) -> str:
        raise RuntimeError("no api key")

    config = JudgeConfig(enabled=True, model="deepseek/deepseek-reasoner")
    result = JudgeProvider(config, backend=backend).evaluate(_trace(), _rubric())

    assert result.status == "error"
    assert "no api key" in result.reason
