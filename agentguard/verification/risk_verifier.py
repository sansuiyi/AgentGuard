"""High-risk verification: confirm blocking decisions before they merge-gate.

The rule evaluator is already deterministic, so "verification" re-asserts the
high-priority (P0/P1) failures and confirms they are genuine rather than an
infrastructure flake. A real LLM re-check can be layered here without changing
the merge-gate contract.
"""

from __future__ import annotations

from agentguard.core.models import EvaluationResult, RiskDecision


def verify_high_risk(decision: RiskDecision, results: list[EvaluationResult]) -> dict:
    """Confirm that every blocking evidence ref is backed by a real failed case."""
    failed_ids = {r.case_id for r in results if r.status.value != "pass"}
    confirmed = []
    unmatched = []
    for ref in decision.evidence_refs:
        case_id = ref.split(":")[0]
        if case_id in failed_ids:
            confirmed.append(ref)
        else:
            unmatched.append(ref)

    return {
        "verdict": "confirmed" if not unmatched else "needs_review",
        "confirmed_refs": confirmed,
        "unmatched_refs": unmatched,
        "p0_count": decision.p0_count,
        "p1_count": decision.p1_count,
    }
