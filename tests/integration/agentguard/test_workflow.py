"""Integration test: full workflow produces the expected decision per scenario."""

from __future__ import annotations

from pathlib import Path

from agentguard.config.loader import load_config
from agentguard.dataset.loader import load_dataset
from agentguard.orchestration.workflow import Workflow
from agentguard.runtime.fault_injection import load_scenarios, resolve_fault_ids


def test_all_scenarios_produce_expected_decision(
    dataset_dir: Path, configs_dir: Path, repo_root: Path, tmp_path: Path
) -> None:
    config = load_config(
        default_path=configs_dir / "default.yaml",
        overrides={"output_dir": str(tmp_path)},
    )
    cases = load_dataset(dataset_dir)
    scenarios = load_scenarios(repo_root / "datasets" / "fault_injection" / "scenarios.yaml")
    workflow = Workflow(config)

    for name, scenario in scenarios.items():
        fault_ids = resolve_fault_ids(name, scenarios)
        report = workflow.run(cases, run_id=f"it-{name}", candidate_faults=set(fault_ids))
        assert report["decision"]["decision"] == scenario["expected_decision"], name


def test_clean_run_has_no_regressions(dataset_dir: Path, configs_dir: Path, tmp_path: Path) -> None:
    config = load_config(default_path=configs_dir / "default.yaml", overrides={"output_dir": str(tmp_path)})
    report = Workflow(config).run(load_dataset(dataset_dir), run_id="it-clean")
    assert report["decision"]["decision"] == "PASS"
    assert report["aggregate"]["regressed"] == []
    assert report["aggregate"]["candidate_passed"] == 300
