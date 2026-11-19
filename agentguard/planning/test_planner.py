"""Test planning: choose cases and produce a run plan."""

from __future__ import annotations

from agentguard.core.models import TestCase
from agentguard.planning.test_selector import select_cases


def plan(
    cases: list[TestCase],
    mode: str,
    categories: list[str] | None = None,
    smoke_count_per_category: int = 1,
) -> dict:
    selected = select_cases(cases, mode, categories, smoke_count_per_category)
    return {
        "mode": mode,
        "total_available": len(cases),
        "selected": len(selected),
        "case_ids": [c.case_id for c in selected],
        "cases": selected,
    }
