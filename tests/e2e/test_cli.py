"""End-to-end CLI tests (run the console entrypoint as a function)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentguard.cli import main


@pytest.fixture(autouse=True)
def _run_from_repo_root(repo_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(repo_root)


def test_dataset_validate_cli(dataset_dir: Path) -> None:
    assert main(["dataset", "validate", "--dataset-dir", str(dataset_dir)]) == 0


def test_dataset_stats_cli(dataset_dir: Path) -> None:
    assert main(["dataset", "stats", "--dataset-dir", str(dataset_dir)]) == 0


def test_demo_clean_cli(dataset_dir: Path, tmp_path: Path) -> None:
    rc = main(
        [
            "demo",
            "--scenario",
            "clean",
            "--dataset-dir",
            str(dataset_dir),
            "--output-dir",
            str(tmp_path),
            "--run-id",
            "e2e-clean",
        ]
    )
    assert rc == 0
    assert (tmp_path / "e2e-clean" / "report.html").exists()
    assert (tmp_path / "e2e-clean" / "summary.json").exists()
    assert (tmp_path / "e2e-clean" / "results.jsonl").exists()


def test_demo_safety_regression_blocks(dataset_dir: Path, tmp_path: Path) -> None:
    rc = main(
        [
            "demo",
            "--scenario",
            "safety-regression",
            "--dataset-dir",
            str(dataset_dir),
            "--output-dir",
            str(tmp_path),
            "--run-id",
            "e2e-safety",
        ]
    )
    assert rc == 0
    summary = json.loads((tmp_path / "e2e-safety" / "summary.json").read_text(encoding="utf-8"))
    assert summary["decision"]["decision"] == "BLOCK"
