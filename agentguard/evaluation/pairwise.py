"""Base-vs-candidate pairwise comparison for a single case."""

from __future__ import annotations

from agentguard.core.models import EvaluationResult, PairwiseResult


def compute_pairwise(base: EvaluationResult, candidate: EvaluationResult) -> PairwiseResult:
    base_passed = base.status.value == "pass"
    candidate_passed = candidate.status.value == "pass"

    if base_passed and candidate_passed:
        regressed = False
        summary = "both_pass"
    elif base_passed and not candidate_passed:
        regressed = True
        summary = "regression"
    elif not base_passed and candidate_passed:
        regressed = False
        summary = "improvement"
    else:
        regressed = False
        summary = "both_fail"

    return PairwiseResult(
        regressed=regressed,
        summary=summary,
        base_passed=base_passed,
        candidate_passed=candidate_passed,
    )
