"""Unit tests for the deterministic demo agent and fault injection."""

from __future__ import annotations

from pathlib import Path

from agentguard.core.enums import Version
from agentguard.core.models import TestCase
from agentguard.dataset.loader import load_dataset
from agentguard.evaluation.rule_evaluator import RuleEvaluator
from agentguard.runtime.demo_agent import (
    FAULT_MEM_WRITE_DISABLED,
    FAULT_PERSONALITY_DRIFT,
    FAULT_SAFETY_SENSITIVE_OFF,
    DemoAgent,
)
from agentguard.runtime.version_runner import VersionRunner


def _case_passes(case: TestCase, faults: set[str]) -> bool:
    agent = DemoAgent(faults=faults)
    runner = VersionRunner(agent, Version.CANDIDATE, "t")
    trace = runner.run_case(case)
    results = RuleEvaluator().evaluate(trace, case.assertions)
    return all(r.passed for r in results)


def _case_by_id(dataset_dir: Path, case_id: str) -> TestCase:
    return next(c for c in load_dataset(dataset_dir) if c.case_id == case_id)


def test_all_clean_cases_pass(dataset_dir: Path) -> None:
    for case in load_dataset(dataset_dir):
        assert _case_passes(case, set()), f"clean case should pass: {case.case_id}"


def test_memory_write_fault_regresses(dataset_dir: Path) -> None:
    case = _case_by_id(dataset_dir, "MEM-001")
    assert not _case_passes(case, {FAULT_MEM_WRITE_DISABLED})


def test_safety_sensitive_fault_regresses(dataset_dir: Path) -> None:
    case = _case_by_id(dataset_dir, "SAFE-001")
    assert not _case_passes(case, {FAULT_SAFETY_SENSITIVE_OFF})


def test_personality_drift_regresses(dataset_dir: Path) -> None:
    case = _case_by_id(dataset_dir, "PER-001")
    assert not _case_passes(case, {FAULT_PERSONALITY_DRIFT})
