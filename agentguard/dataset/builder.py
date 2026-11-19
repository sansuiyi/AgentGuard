"""Dataset build helpers: stats, manifest generation, and template export.

The golden JSONL files are human-authored (source of truth); ``build`` assembles
the manifest and statistics from them rather than generating cases from an LLM.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from agentguard.core.errors import DatasetValidationError
from agentguard.dataset.loader import load_dataset
from agentguard.dataset.registry import CATEGORY_NAMES
from agentguard.dataset.validator import validate_dataset

TEMPLATE_CASE: dict[str, Any] = {
    "case_id": "MEM-000",
    "title": "",
    "category": "memory",
    "tags": [],
    "priority": "P2",
    "description": "",
    "user_profile": {"user_id": "demo-user-000", "facts": []},
    "turns": [{"input": "", "expected": {}}],
    "assertions": [{"type": "response_contains", "text": ""}],
    "judge_rubric": None,
    "expected_capabilities": [],
    "metadata": {"source": "human_authored", "version": "1.0"},
}


def stats(dataset_dir: str | Path) -> dict[str, Any]:
    """Aggregate case counts, priorities, assertion types and sources."""
    cases = load_dataset(dataset_dir)
    per_category: dict[str, int] = {c: 0 for c in CATEGORY_NAMES}
    priorities: Counter[str] = Counter()
    assertion_types: Counter[str] = Counter()
    sources: Counter[str] = Counter()
    capabilities: Counter[str] = Counter()

    for case in cases:
        per_category[case.category.value] += 1
        priorities[case.priority.value] += 1
        for a in case.assertions:
            assertion_types[a.type] += 1
        for c in case.expected_capabilities:
            capabilities[c] += 1
        sources[case.metadata.get("source", "unknown")] += 1

    return {
        "total": len(cases),
        "categories": per_category,
        "priorities": dict(priorities),
        "assertion_types": dict(assertion_types),
        "capabilities": dict(capabilities),
        "sources": dict(sources),
    }


def build_manifest(dataset_dir: str | Path, manifest_path: str | Path) -> dict[str, Any]:
    """Validate the dataset and write ``datasets/manifest.yaml``."""
    report = validate_dataset(dataset_dir)
    if not report.valid:
        raise DatasetValidationError(
            f"cannot build manifest: dataset invalid ({len(report.issues)} issue(s))",
            context={"issues": [i.__dict__ for i in report.issues]},
        )

    manifest: dict[str, Any] = {
        "dataset_name": "agentguard-golden",
        "dataset_version": "1.0.0",
        "case_count": report.case_count,
        "categories": report.category_counts,
    }
    Path(manifest_path).write_text(
        yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return manifest


def export_template(category: str, out_path: str | Path) -> None:
    """Write a single-case JSONL template for the given category."""
    if category not in CATEGORY_NAMES:
        raise DatasetValidationError(f"unknown category {category!r}", context={"category": category})
    template = dict(TEMPLATE_CASE)
    template["case_id"] = f"{category[:3].upper()}-000"
    template["category"] = category
    Path(out_path).write_text(
        yaml.safe_dump(template, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
