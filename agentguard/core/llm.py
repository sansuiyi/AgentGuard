"""Thin wrapper over the existing AI handler used by the AgentGuard agent.

Reuses ``LiteLLMAIHandler`` (the repository default) via the same factory
pattern as ``PRAgent``, and reads the model name from ``config.model`` rather
than introducing a second configuration system. Tests inject a ``MockHandler``
factory instead so no real API key or network is needed.

Model selection is configuration-driven, never hard-coded: the review (first
pass) and verify (second pass) steps may use different models via
``[agent_exec].review_model`` / ``verify_model``. An empty value falls back to
``config.model``, so swapping a model is a configuration change only.
"""

from typing import Any, Optional

from pr_agent.algo.ai_handlers.litellm_ai_handler import LiteLLMAIHandler
from pr_agent.config_loader import get_settings


class AgentLLM:
    """Minimal async interface to the shared AI handler."""

    def __init__(
        self,
        ai_handler_factory=LiteLLMAIHandler,
        model: Optional[str] = None,
        handler: Any = None,
    ) -> None:
        self._factory = ai_handler_factory
        # A shared handler lets the review and verify passes use different
        # model names without building a second provider client.
        self._handler = handler if handler is not None else ai_handler_factory()
        self._model = model or None

    @property
    def handler(self) -> Any:
        return self._handler

    def model_name(self) -> str:
        if self._model:
            return self._model
        # Tolerate a partially-loaded settings object (e.g. in unit tests) by
        # falling back through .get(); production always has config.model set.
        config = get_settings().get("config", {}) or {}
        return config.get("model", "gpt-5.6")

    def with_model(self, model: Optional[str]) -> "AgentLLM":
        """Return a sibling LLM sharing this handler but with a model override.

        Returns ``self`` when no distinct model is configured, so the default
        path keeps exactly one handler instance (and one client) per run.
        """
        if not model or model == self.model_name():
            return self
        return AgentLLM(model=model, handler=self._handler, ai_handler_factory=self._factory)

    async def complete(self, system: str, user: str, temperature: float = 0.2) -> tuple[str, Any]:
        """Return ``(content, finish_reason)`` from the underlying handler."""
        resp, finish_reason = await self._handler.chat_completion(
            model=self.model_name(),
            system=system,
            user=user,
            temperature=temperature,
        )
        return resp, finish_reason
