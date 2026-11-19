"""Test selection strategies."""

from __future__ import annotations

from agentguard.core.enums import Priority
from agentguard.core.models import TestCase

_PRIORITY_ORDER = {Priority.P0: 0, Priority.P1: 1, Priority.P2: 2, Priority.P3: 3}


def select_cases(
    cases: list[TestCase],
    mode: str,
    categories: list[str] | None = None,
    smoke_count_per_category: int = 1,
) -> list[TestCase]:
    """Select cases per the requested mode.

    ``full`` returns everything; ``smoke`` returns a per-category sample;
    ``impact`` falls back to ``full`` in the MVP (no diff index yet); and
    ``risk_based`` returns all P0/P1 cases plus non-critical cases sorted by risk.
    """
    if categories:
        cases = [c for c in cases if c.category.value in categories]

    if mode == "smoke":
        return _smoke(cases, smoke_count_per_category)
    if mode == "risk_based":
        return _risk_based(cases)
    # "full" and "impact" (no diff index yet) both return the whole set.
    return cases


def _smoke(cases: list[TestCase], per_category: int) -> list[TestCase]:
    """Take the highest-risk ``per_category`` cases from each category.

    Ordering by priority then case id keeps the sample deterministic and biases
    it toward P0/P1 cases, while the original dataset order is preserved in the
    returned list.
    """
    selected_ids: set[str] = set()
    categories = dict.fromkeys(c.category.value for c in cases)
    for category in categories:
        ordered = sorted(
            (c for c in cases if c.category.value == category),
            key=lambda c: (_PRIORITY_ORDER[c.priority], c.case_id),
        )
        selected_ids.update(c.case_id for c in ordered[:per_category])
    # preserve deterministic order by original list
    return [c for c in cases if c.case_id in selected_ids]


def _risk_based(cases: list[TestCase]) -> list[TestCase]:
    ordered = sorted(cases, key=lambda c: (_PRIORITY_ORDER[c.priority], c.case_id))
    return ordered
