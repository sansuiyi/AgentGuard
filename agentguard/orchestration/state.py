"""Shared LangGraph state for the bounded OODA agent loop."""

import operator
from typing import Annotated, Any, List, Optional, TypedDict

from agentguard.core.schemas import AuditEvent, Decision, Finding, ToolResult, TrajectoryStep


class AgentGraphState(TypedDict, total=False):
    """State passed between orchestration nodes.

    ``messages`` uses ``operator.add`` so nodes return only their *incremental*
    message list and the graph concatenates them, keeping the trajectory auditable
    without relying on LangGraph's tool-call pairing semantics. All other fields are
    plain (overwritten) fields, so nodes return the full updated list.
    """

    messages: Annotated[List[Any], operator.add]
    findings: List[Finding]
    tool_results: List[ToolResult]
    decision: Optional[Decision]
    step: int
    final_answer: Optional[str]
    orientation: Optional[str]
    decision_history: List[str]
    audit_events: List[AuditEvent]
    trajectory: List[TrajectoryStep]
