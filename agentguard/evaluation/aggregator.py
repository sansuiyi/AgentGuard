"""Aggregate per-case results into a run-level summary."""

from __future__ import annotations

from collections import Counter, defaultdict

from agentguard.core.models import EvaluationResult


def aggregate(results: list[EvaluationResult], run_id: str, category_map: dict[str, str] | None = None) -> dict:
    """Summarize candidate-side outcomes and pairwise regressions for a run."""
    category_map = category_map or {}
    total = len(results)
    candidate_passed = sum(1 for r in results if r.status.value == "pass")
    candidate_failed = sum(1 for r in results if r.status.value == "fail")
    candidate_error = sum(1 for r in results if r.status.value == "error")

    regressed: list[str] = []
    improved: list[str] = []
    both_fail: list[str] = []
    both_pass = 0
    for r in results:
        p = r.pairwise_result
        if p is None:
            continue
        if p.summary == "regression":
            regressed.append(r.case_id)
        elif p.summary == "improvement":
            improved.append(r.case_id)
        elif p.summary == "both_fail":
            both_fail.append(r.case_id)
        elif p.summary == "both_pass":
            both_pass += 1

    categories: dict[str, dict[str, int]] = defaultdict(lambda: Counter())
    for r in results:
        category = category_map.get(r.case_id, r.case_id.split("-")[0].lower())
        categories[category][r.status.value] += 1

    return {
        "run_id": run_id,
        "total": total,
        "candidate_passed": candidate_passed,
        "candidate_failed": candidate_failed,
        "candidate_error": candidate_error,
        "regressed": regressed,
        "improved": improved,
        "both_fail": both_fail,
        "both_pass": both_pass,
        "categories": {k: dict(v) for k, v in categories.items()},
    }
