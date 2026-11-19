"""Agent adapter protocol and shared runtime types.

The demo agent is synchronous; a future real-agent adapter may be async. The
protocol is the single contract the version runner depends on, so any backend
that satisfies it can be plugged in without touching evaluation or reporting.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from agentguard.core.models import MemoryOp, StateSnapshot, ToolCall, UserProfile


@dataclass
class InvokeResult:
    """Result of a single ``invoke`` call."""

    response: str
    memory_reads: list[MemoryOp] = field(default_factory=list)
    memory_writes: list[MemoryOp] = field(default_factory=list)
    tool_calls: list[ToolCall] = field(default_factory=list)
    state_before: StateSnapshot = field(default_factory=StateSnapshot)
    state_after: StateSnapshot = field(default_factory=StateSnapshot)
    latency_ms: float = 0.0


@runtime_checkable
class AgentAdapter(Protocol):
    """Uniform interface the version runner executes against."""

    def setup(self, config: dict) -> None: ...

    def reset(self, user_profile: UserProfile) -> None: ...

    def invoke(self, message: str, history: list[dict]) -> InvokeResult: ...

    def collect_trace(self) -> dict: ...

    def teardown(self) -> None: ...
