"""Unit tests for the deterministic risk-decision engine."""

from __future__ import annotations

from agentguard.config.schemas import PolicyConfig
from agentguard.core.enums import CaseStatus, Category, DecisionStatus, Priority, Version
from agentguard.core.models import (
    Assertion,
    EvaluationResult,
    PairwiseResult,
    RiskDecision,
    TestCase,
    Turn,
    UserProfile,
)
from agentguard.decision.risk_engine import RiskEngine


def _case(case_id: str, priority: str) -> TestCase:
    return TestCase(
        case_id=case_id,
        title="t",
        category=Category.MEMORY,
        priority=Priority(priority),
        user_profile=UserProfile(user_id="u"),
        turns=[Turn(input="hi")],
        assertions=[Assertion(type="response_contains", text="x")],
    )


def _result(case_id: str, status: str, regressed: bool = False) -> EvaluationResult:
    return EvaluationResult(
        case_id=case_id,
        version=Version.CANDIDATE,
        status=CaseStatus(status),
        pairwise_result=PairwiseResult(regressed=regressed, summary="regression" if regressed else "both_fail"),
    )


def _decide(cases: list[TestCase], results: list[EvaluationResult]) -> RiskDecision:
    return RiskEngine(PolicyConfig()).decide("r", {c.case_id: c for c in cases}, results)


def test_no_failures_is_pass() -> None:
    decision = _decide([_case("C1", "P2")], [_result("C1", "pass")])
    assert decision.decision == DecisionStatus.PASS


def test_p0_failure_blocks() -> None:
    decision = _decide([_case("SAFE-1", "P0")], [_result("SAFE-1", "fail")])
    assert decision.decision == DecisionStatus.BLOCK


def test_p1_confirmed_regression_blocks() -> None:
    decision = _decide([_case("MEM-1", "P1")], [_result("MEM-1", "fail", regressed=True)])
    assert decision.decision == DecisionStatus.BLOCK


def test_p1_insufficient_evidence_reviews() -> None:
    decision = _decide([_case("MEM-1", "P1")], [_result("MEM-1", "fail", regressed=False)])
    assert decision.decision == DecisionStatus.REVIEW


def test_p2_failure_reviews() -> None:
    decision = _decide([_case("EMO-1", "P2")], [_result("EMO-1", "fail")])
    assert decision.decision == DecisionStatus.REVIEW


def test_candidate_error_is_error() -> None:
    decision = _decide([_case("C1", "P2")], [_result("C1", "error")])
    assert decision.decision == DecisionStatus.ERROR
