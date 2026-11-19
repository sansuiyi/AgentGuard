"""Deterministic risk-decision engine.

Maps per-case outcomes + priorities to one of the four allowed decisions
(PASS / REVIEW / BLOCK / ERROR). No LLM, no thresholds hidden in code — all
knobs come from ``PolicyConfig``.
"""

from __future__ import annotations

from datetime import datetime, timezone

from agentguard.config.schemas import PolicyConfig
from agentguard.core.enums import DecisionStatus
from agentguard.core.models import EvaluationResult, RiskDecision, TestCase

_ERROR = DecisionStatus.ERROR
_BLOCK = DecisionStatus.BLOCK
_REVIEW = DecisionStatus.REVIEW
_PASS = DecisionStatus.PASS


class RiskEngine:
    """Aggregates candidate-side failures into a merge-gate decision."""

    def __init__(self, policy: PolicyConfig, policy_version: str = "1.0.0") -> None:
        self._policy = policy
        self._policy_version = policy_version

    def decide(
        self,
        run_id: str,
        case_index: dict[str, TestCase],
        results: list[EvaluationResult],
    ) -> RiskDecision:
        p0_count = 0
        p1_count = 0
        warnings: list[str] = []
        evidence: list[str] = []

        for result in results:
            if result.status.value == "pass":
                continue

            case = case_index.get(result.case_id)
            priority = case.priority.value if case else "P2"
            regressed = bool(result.pairwise_result and result.pairwise_result.regressed)

            if result.status.value == "error":
                evidence.append(f"{result.case_id}:candidate_error")
                continue

            if priority == "P0":
                p0_count += 1
                evidence.append(f"{result.case_id}:P0_failure")
            elif priority == "P1":
                p1_count += 1
                if regressed:
                    evidence.append(f"{result.case_id}:P1_confirmed_regression")
                else:
                    evidence.append(f"{result.case_id}:P1_insufficient_evidence")
            else:
                warnings.append(f"{result.case_id}:P{priority[1:]} non-critical failure")

        decision, reason = self._resolve(evidence, warnings, p0_count, p1_count)

        return RiskDecision(
            run_id=run_id,
            decision=decision,
            decision_reason=reason,
            evidence_refs=evidence,
            policy_version=self._policy_version,
            timestamp=datetime.now(timezone.utc).isoformat(),
            p0_count=p0_count,
            p1_count=p1_count,
            warnings=warnings,
        )

    def _resolve(
        self,
        evidence: list[str],
        warnings: list[str],
        p0_count: int,
        p1_count: int,
    ) -> tuple[DecisionStatus, str]:
        has_error = any(e.endswith(":candidate_error") for e in evidence)
        has_p0 = p0_count > 0
        has_confirmed_p1 = any(e.endswith(":P1_confirmed_regression") for e in evidence)
        has_p1_insufficient = any(e.endswith(":P1_insufficient_evidence") for e in evidence)

        if has_p0 and self._policy.block_on_p0_safety:
            return _BLOCK, f"{p0_count} P0 safety failure(s); blocking merge."
        if has_confirmed_p1 and self._policy.block_on_confirmed_p1_regression:
            return _BLOCK, f"{p1_count} P1 case(s), with confirmed regression; blocking merge."
        if has_error:
            return _ERROR, "candidate crashed on one or more cases; re-run required."
        if has_p0 or has_p1_insufficient or has_confirmed_p1:
            status = _policy_status(self._policy.p1_insufficient_evidence)
            reasons: list[str] = []
            if has_p0:
                reasons.append(f"{p0_count} P0 failure(s)")
            if p1_count:
                reasons.append(f"{p1_count} P1 case(s) without confirmed regression")
            return status, f"{'; '.join(reasons)}; policy requires {status.value}."
        if warnings:
            status = _policy_status(self._policy.p2_p3_noncritical)
            return status, f"{len(warnings)} non-critical (P2/P3) failure(s); policy requires {status.value}."
        return _PASS, "no regressions or safety violations detected."


def _policy_status(value: str) -> DecisionStatus:
    """Map a policy fallback string to a decision, defaulting to REVIEW."""
    try:
        return DecisionStatus(value)
    except ValueError:
        return _REVIEW
