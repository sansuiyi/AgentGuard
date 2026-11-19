"""Merge gate: translate a risk decision into a concrete merge action."""

from __future__ import annotations

from agentguard.core.enums import DecisionStatus
from agentguard.core.models import RiskDecision

_ACTION_BY_DECISION = {
    DecisionStatus.PASS: "merge",
    DecisionStatus.REVIEW: "hold",
    DecisionStatus.BLOCK: "reject",
    DecisionStatus.ERROR: "reject",
}


def merge_action(decision: RiskDecision) -> dict:
    """Return the actionable gate output for a given risk decision."""
    return {
        "action": _ACTION_BY_DECISION[decision.decision],
        "decision": decision.decision.value,
        "reason": decision.decision_reason,
        "evidence_refs": decision.evidence_refs,
    }
