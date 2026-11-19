"""Unit tests for dataset loading, validation, and stats."""

from __future__ import annotations

from pathlib import Path

import pytest

from agentguard.core.errors import DatasetValidationError
from agentguard.dataset.builder import stats
from agentguard.dataset.loader import load_dataset, load_jsonl
from agentguard.dataset.validator import validate_dataset


def test_load_dataset_has_three_hundred_cases(dataset_dir: Path) -> None:
    cases = load_dataset(dataset_dir)
    assert len(cases) == 300
    assert {c.category.value for c in cases} == {"memory", "emotion", "personality", "safety", "tool_state"}


def test_validate_dataset_is_valid(dataset_dir: Path) -> None:
    report = validate_dataset(dataset_dir)
    assert report.valid
    assert report.case_count == 300
    assert report.category_counts["memory"] == 60


def test_stats_counts(dataset_dir: Path) -> None:
    s = stats(dataset_dir)
    assert s["total"] == 300
    assert s["categories"]["safety"] == 60
    assert s["sources"].get("human_authored") == 20


def test_load_jsonl_malformed_line_raises(tmp_path: Path) -> None:
    p = tmp_path / "bad.jsonl"
    p.write_text('{"case_id": "X"}\n{not json}\n', encoding="utf-8")
    with pytest.raises(DatasetValidationError):
        load_jsonl(p)


def test_validate_case_rejects_unknown_assertion(tmp_path: Path) -> None:
    (tmp_path / "memory.jsonl").write_text(
        '{"case_id": "MEM-X", "title": "x", "category": "memory", "priority": "P2", '
        '"user_profile": {"user_id": "u", "facts": []}, "turns": [{"input": "hi"}], '
        '"assertions": [{"type": "no_such_assertion"}]}\n',
        encoding="utf-8",
    )
    report = validate_dataset(tmp_path)
    assert not report.valid
    assert any("unknown assertion type" in i.message for i in report.issues)
