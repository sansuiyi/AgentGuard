"""Unit tests for high-risk verification before the merge gate."""

from __future__ import annotations

from agentguard.core.enums import CaseStatus, DecisionStatus, Version
from agentguard.core.models import EvaluationResult, RiskDecision
from agentguard.verification.risk_verifier import verify_high_risk


def _decision(refs: list[str]) -> RiskDecision:
    return RiskDecision(
        run_id="run-1",
        decision=DecisionStatus.BLOCK,
        decision_reason="blocked",
        evidence_refs=refs,
        p0_count=1,
    )


def _result(case_id: str, status: str) -> EvaluationResult:
    return EvaluationResult(case_id=case_id, version=Version.CANDIDATE, status=CaseStatus(status))


def test_confirmed_refs_pass_verification() -> None:
    verdict = verify_high_risk(_decision(["SAFE-001:P0_failure"]), [_result("SAFE-001", "fail")])
    assert verdict["verdict"] == "confirmed"
    assert verdict["confirmed_refs"] == ["SAFE-001:P0_failure"]
    assert verdict["unmatched_refs"] == []


def test_missing_case_needs_review() -> None:
    verdict = verify_high_risk(_decision(["SAFE-999:P0_failure"]), [_result("SAFE-001", "fail")])
    assert verdict["verdict"] == "needs_review"
    assert verdict["unmatched_refs"] == ["SAFE-999:P0_failure"]


def test_empty_evidence_is_confirmed() -> None:
    verdict = verify_high_risk(_decision([]), [_result("SAFE-001", "pass")])
    assert verdict["verdict"] == "confirmed"
