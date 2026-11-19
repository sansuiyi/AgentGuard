"""JSONL dataset loading for the golden test set.

Each line is an independent JSON object (never a JSON array wrapping many cases).
Parse errors report the file and line number so a broken case is fixable fast.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

from agentguard.core.errors import DatasetValidationError
from agentguard.core.models import TestCase
from agentguard.dataset.registry import CATEGORY_NAMES


def load_jsonl(path: str | Path) -> list[dict]:
    """Parse a JSONL file into a list of raw dicts, failing on any malformed line."""
    p = Path(path)
    if not p.exists():
        raise DatasetValidationError(f"dataset file not found: {p}", context={"path": str(p)})

    records: list[dict] = []
    with p.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                obj = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise DatasetValidationError(
                    f"invalid JSON on {p}:{line_no}: {exc}",
                    context={"path": str(p), "line": line_no},
                ) from exc
            if not isinstance(obj, dict):
                raise DatasetValidationError(
                    f"expected JSON object on {p}:{line_no}, got {type(obj).__name__}",
                    context={"path": str(p), "line": line_no},
                )
            records.append(obj)
    return records


def category_file(dataset_dir: str | Path, category: str) -> Path:
    return Path(dataset_dir) / f"{category}.jsonl"


def iter_category_files(dataset_dir: str | Path) -> Iterator[tuple[str, Path]]:
    for category in CATEGORY_NAMES:
        yield category, category_file(dataset_dir, category)


def load_dataset(dataset_dir: str | Path) -> list[TestCase]:
    """Load and validate every case across all five category files."""
    cases: list[TestCase] = []
    for _, path in iter_category_files(dataset_dir):
        for raw in load_jsonl(path):
            cases.append(TestCase.model_validate(raw))
    return cases


def load_cases_by_category(dataset_dir: str | Path, category: str) -> list[TestCase]:
    path = category_file(dataset_dir, category)
    return [TestCase.model_validate(raw) for raw in load_jsonl(path)]
