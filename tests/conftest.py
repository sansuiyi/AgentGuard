"""Shared fixtures for AgentGuard tests (all test roots under ``tests/``)."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def disable_llm_judge(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the suite offline and deterministic: never call a real judge model."""
    monkeypatch.setenv("AGENTGUARD_JUDGE_ENABLED", "false")


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


@pytest.fixture
def dataset_dir(repo_root: Path) -> Path:
    return repo_root / "datasets" / "golden"


@pytest.fixture
def configs_dir(repo_root: Path) -> Path:
    return repo_root / "configs"
