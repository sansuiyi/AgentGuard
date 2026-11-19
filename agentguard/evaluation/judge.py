"""Optional LLM-as-Judge.

The deterministic demo must run fully offline, so a judge is never required:
when no model is configured the provider returns ``status="unavailable"`` and the
rule evaluator's result is used unchanged. This keeps the extension point clean
without blocking the base pipeline.

Model selection is configurable via ``JudgeConfig`` / ``AGENTGUARD_JUDGE_MODEL``.
A judge backend is injectable so tests stay deterministic and offline.
"""

from __future__ import annotations

import json
import os
import tomllib
from collections.abc import Callable
from pathlib import Path
from typing import Any

from agentguard.config.schemas import JudgeConfig
from agentguard.core.models import AgentTrace, JudgeResult, JudgeRubric

JudgeBackend = Callable[[JudgeConfig, str], str]

# Provider prefix -> (env var, section name in pr_agent/settings/.secrets.toml).
# When neither source has a key the judge reports ``unavailable`` instead of
# letting LiteLLM fail loudly.
_PROVIDERS: dict[str, tuple[str, str]] = {
    "deepseek/": ("DEEPSEEK_API_KEY", "deepseek"),
    "openai/": ("OPENAI_API_KEY", "openai"),
}

_SECRETS_PATH = Path(__file__).resolve().parents[2] / "pr_agent" / "settings" / ".secrets.toml"

_SYSTEM_PROMPT = (
    "You are an impartial evaluator for a companion agent's behavior. "
    "Read the rubric and the conversation, then score the agent from 1 to 5. "
    'Reply with JSON only: {"score": <int>, "passed": <bool>, '
    '"reason": "<short>", "evidence": "<quote>"}.'
)


def _render_prompt(trace: AgentTrace, rubric: JudgeRubric) -> str:
    lines = [
        f"Rubric: {rubric.question}",
        f"Pass threshold: {rubric.pass_threshold}",
    ]
    if rubric.dimensions:
        lines.append("Dimensions: " + ", ".join(rubric.dimensions))
    lines.append("Conversation:")
    for turn in trace.turns:
        lines.append(f"User: {turn.user_input}")
        lines.append(f"Agent: {turn.agent_response}")
    lines.append(f"Final memory: {trace.final_memory}")
    lines.append(f"Final emotion: {trace.final_emotion}")
    return "\n".join(lines)


def _litellm_backend(config: JudgeConfig, prompt: str) -> str:
    """Call the configured model through LiteLLM (imported lazily, offline-safe)."""
    import litellm

    kwargs: dict[str, Any] = {}
    api_key = _resolve_api_key(config.model)
    if api_key:
        kwargs["api_key"] = api_key
    response = litellm.completion(
        model=config.model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=config.temperature,
        timeout=config.timeout_seconds,
        num_retries=config.max_retries,
        **kwargs,
    )
    return response.choices[0].message.content or ""


def _secret_api_key(provider: str) -> str | None:
    """Read ``[<provider>] key`` from the gitignored pr_agent secrets file."""
    if not _SECRETS_PATH.exists():
        return None
    try:
        data = tomllib.loads(_SECRETS_PATH.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return None
    section = data.get(provider)
    if isinstance(section, dict):
        key = section.get("key")
        if isinstance(key, str) and key.strip():
            return key.strip()
    return None


def _resolve_api_key(model: str) -> str | None:
    for prefix, (env_name, provider) in _PROVIDERS.items():
        if model.startswith(prefix):
            return os.environ.get(env_name) or _secret_api_key(provider)
    return None


def _missing_api_key(model: str) -> str | None:
    for prefix, (env_name, _provider) in _PROVIDERS.items():
        if model.startswith(prefix) and not _resolve_api_key(model):
            return env_name
    return None


def _parse_payload(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.startswith("json"):
            text = text[4:].strip()
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("judge payload must be a JSON object")
    return data


class JudgeProvider:
    """Wraps an optional LLM judge. Offline by default."""

    def __init__(self, config: JudgeConfig, backend: JudgeBackend | None = None) -> None:
        self._config = config
        self._backend = backend

    @property
    def available(self) -> bool:
        return self._config.enabled and bool(self._config.model)

    def evaluate(self, trace: AgentTrace, rubric: JudgeRubric | None) -> JudgeResult:
        if rubric is None:
            return JudgeResult(status="unavailable", reason="no judge rubric for this case")
        if not self.available:
            return JudgeResult(status="unavailable", reason="LLM judge not configured")

        if self._backend is None:
            missing = _missing_api_key(self._config.model)
            if missing:
                return JudgeResult(
                    status="unavailable",
                    reason=f"missing {missing} for judge model {self._config.model}",
                )

        backend = self._backend or _litellm_backend
        try:
            payload = _parse_payload(backend(self._config, _render_prompt(trace, rubric)))
        except Exception as exc:  # a judge failure must never block the run
            return JudgeResult(status="error", reason=f"judge backend failed: {exc}")

        score = int(payload.get("score", 0))
        passed = payload.get("passed")
        if passed is None:
            passed = score >= rubric.pass_threshold
        return JudgeResult(
            score=score,
            passed=bool(passed),
            reason=str(payload.get("reason", "")),
            evidence=str(payload.get("evidence", "")),
            status="available",
        )
