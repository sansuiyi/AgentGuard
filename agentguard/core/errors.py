"""Typed errors for the AgentGuard behavior-testing platform.

Every pipeline failure carries context so it can be traced back to a case, a
file, a line number, or a version — never swallowed by a bare ``except``.
"""

from __future__ import annotations

from typing import Any


class AgentGuardError(Exception):
    """Base class for all behavior-platform errors."""

    def __init__(self, message: str, *, context: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.context = context or {}

    def __str__(self) -> str:  # noqa: D401 - informative message
        if self.context:
            return f"{self.message} (context={self.context})"
        return self.message


class DatasetValidationError(AgentGuardError):
    """The golden dataset failed schema validation."""


class AssertionTypeError(AgentGuardError):
    """An assertion references a type not present in the assertion registry."""


class ConfigError(AgentGuardError):
    """Configuration is missing, malformed, or contradictory."""


class RuntimeExecutionError(AgentGuardError):
    """A versioned run failed (adapter crash, timeout, missing trace)."""


class TraceMissingError(AgentGuardError):
    """A required trace was not produced for a case/version pair."""
