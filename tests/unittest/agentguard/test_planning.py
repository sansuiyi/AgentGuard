"""Unit tests for dataset selection strategies."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from agentguard.dataset.loader import load_dataset
from agentguard.planning.test_selector import select_cases


def test_smoke_selection_takes_ten_per_category(dataset_dir: Path) -> None:
    cases = load_dataset(dataset_dir)
    selected = select_cases(cases, "smoke", smoke_count_per_category=10)
    assert len(selected) == 50
    assert Counter(c.category.value for c in selected) == {
        "memory": 10,
        "emotion": 10,
        "personality": 10,
        "safety": 10,
        "tool_state": 10,
    }


def test_smoke_selection_prefers_higher_priority(dataset_dir: Path) -> None:
    cases = load_dataset(dataset_dir)
    selected = select_cases(cases, "smoke", smoke_count_per_category=1)
    for category in {c.category.value for c in cases}:
        best = min(c.priority.value for c in cases if c.category.value == category)
        picked = [c for c in selected if c.category.value == category]
        assert len(picked) == 1
        assert picked[0].priority.value == best


def test_full_selection_returns_all(dataset_dir: Path) -> None:
    cases = load_dataset(dataset_dir)
    assert len(select_cases(cases, "full")) == 300
