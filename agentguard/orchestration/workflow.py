"""Behavior-testing pipeline orchestration.

Ties together selection -> dual-version execution -> rule evaluation -> pairwise
regression -> risk decision -> verification -> merge gate -> reporting. This is
the single entry point that both ``run`` and ``demo`` commands call.
"""

from __future__ import annotations

from pathlib import Path

from agentguard.config.schemas import Config
from agentguard.core.enums import CaseStatus, Version
from agentguard.core.models import EvaluationResult, TestCase
from agentguard.decision.merge_gate import merge_action
from agentguard.decision.risk_engine import RiskEngine
from agentguard.evaluation.aggregator import aggregate
from agentguard.evaluation.judge import JudgeProvider
from agentguard.evaluation.pairwise import compute_pairwise
from agentguard.evaluation.rule_evaluator import RuleEvaluator
from agentguard.runtime.demo_agent import DemoAgent
from agentguard.runtime.version_runner import VersionRunner
from agentguard.tracing.store import TraceStore
from agentguard.verification.risk_verifier import verify_high_risk


def _status_for(trace_status: str, passed: bool) -> CaseStatus:
    if trace_status == "error":
        return CaseStatus.ERROR
    return CaseStatus.PASS if passed else CaseStatus.FAIL


class Workflow:
    """Deterministic end-to-end behavior-regression run."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._evaluator = RuleEvaluator()
        self._judge = JudgeProvider(config.judge)
        self._risk_engine = RiskEngine(config.policy)

    def run(
        self,
        cases: list[TestCase],
        run_id: str,
        base_faults: set[str] | None = None,
        candidate_faults: set[str] | None = None,
    ) -> dict:
        base_faults = base_faults or set()
        candidate_faults = candidate_faults or set()

        demo_config = self._config.demo.model_dump()
        base_agent = DemoAgent(config=demo_config, faults=set(base_faults))
        candidate_agent = DemoAgent(config=demo_config, faults=set(candidate_faults))
        base_runner = VersionRunner(base_agent, Version.BASE, run_id)
        candidate_runner = VersionRunner(candidate_agent, Version.CANDIDATE, run_id)

        trace_store = TraceStore(Path(self._config.output_dir) / run_id / "traces")

        case_index: dict[str, TestCase] = {c.case_id: c for c in cases}
        candidate_results: list[EvaluationResult] = []
        case_records: list[dict] = []

        for case in cases:
            base_trace = base_runner.run_case(case)
            candidate_trace = candidate_runner.run_case(case)

            base_rule = self._evaluator.evaluate(base_trace, case.assertions)
            candidate_rule = self._evaluator.evaluate(candidate_trace, case.assertions)

            base_passed = self._evaluator.all_passed(base_rule)
            candidate_passed = self._evaluator.all_passed(candidate_rule)

            base_eval = EvaluationResult(
                case_id=case.case_id,
                version=Version.BASE,
                rule_results=base_rule,
                judge_result=self._judge.evaluate(base_trace, case.judge_rubric),
                absolute_score=self._score(base_rule),
                status=_status_for(base_trace.status, base_passed),
            )
            candidate_eval = EvaluationResult(
                case_id=case.case_id,
                version=Version.CANDIDATE,
                rule_results=candidate_rule,
                judge_result=self._judge.evaluate(candidate_trace, case.judge_rubric),
                absolute_score=self._score(candidate_rule),
                status=_status_for(candidate_trace.status, candidate_passed),
            )

            pairwise = compute_pairwise(base_eval, candidate_eval)
            base_eval.pairwise_result = pairwise
            candidate_eval.pairwise_result = pairwise

            trace_store.save(base_trace)
            trace_store.save(candidate_trace)

            candidate_results.append(candidate_eval)
            case_records.append(
                {
                    "case_id": case.case_id,
                    "title": case.title,
                    "category": case.category.value,
                    "priority": case.priority.value,
                    "base": base_eval.model_dump(mode="json"),
                    "candidate": candidate_eval.model_dump(mode="json"),
                    "pairwise": pairwise.model_dump(mode="json"),
                }
            )

        base_runner.teardown()
        candidate_runner.teardown()

        summary = aggregate(candidate_results, run_id, category_map={c.case_id: c.category.value for c in cases})
        decision = self._risk_engine.decide(run_id, case_index, candidate_results)
        verification = verify_high_risk(decision, candidate_results)
        action = merge_action(decision)

        return {
            "run_id": run_id,
            "case_records": case_records,
            "aggregate": summary,
            "decision": decision.model_dump(mode="json"),
            "verification": verification,
            "merge_action": action,
        }

    @staticmethod
    def _score(results) -> float:
        if not results:
            return 0.0
        return round(sum(1 for r in results if r.passed) / len(results), 4)
