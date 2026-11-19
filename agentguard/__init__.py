"""AgentGuard: PR-level behavioral quality assurance for companion agents.

The package hosts two cooperating subsystems:

* the **behavior-testing platform** (``agentguard.core.models``,
  ``agentguard.dataset``, ``agentguard.runtime``, ``agentguard.evaluation``,
  ``agentguard.decision``, ``agentguard.reporting``, ``agentguard.cli``) — a
  deterministic offline regression harness;
* the **code-review agent framework** (``agentguard.core.schemas``,
  ``agentguard.orchestration``) — the bounded OODA review loop.

Review-framework symbols are imported lazily so the offline CLI never pulls in
``pr_agent`` / Dynaconf unless the review loop is actually used.
"""

from __future__ import annotations

import importlib
from typing import Any

__all__ = [
    "AgentState",
    "AuditEvent",
    "Decision",
    "Finding",
    "ReviewAgentRunner",
    "ToolResult",
    "TrajectoryStep",
]

_LAZY: dict[str, tuple[str, str]] = {
    "AgentState": ("agentguard.core.schemas", "AgentState"),
    "AuditEvent": ("agentguard.core.schemas", "AuditEvent"),
    "Decision": ("agentguard.core.schemas", "Decision"),
    "Finding": ("agentguard.core.schemas", "Finding"),
    "ToolResult": ("agentguard.core.schemas", "ToolResult"),
    "TrajectoryStep": ("agentguard.core.schemas", "TrajectoryStep"),
    "ReviewAgentRunner": ("agentguard.orchestration.runner", "ReviewAgentRunner"),
}


def __getattr__(name: str) -> Any:
    if name in _LAZY:
        module_name, attr = _LAZY[name]
        value = getattr(importlib.import_module(module_name), attr)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_LAZY))
