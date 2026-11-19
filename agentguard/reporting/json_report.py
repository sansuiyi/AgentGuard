"""JSON report writers: run summary + per-case JSONL."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_summary(report: dict, path: str | Path) -> Path:
    """Write the run-level summary (decision, aggregate, verification)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    summary = {
        "run_id": report["run_id"],
        "decision": report["decision"],
        "aggregate": report["aggregate"],
        "verification": report["verification"],
        "merge_action": report["merge_action"],
    }
    p.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def write_results_jsonl(report: dict, path: str | Path) -> Path:
    """Write one line per case (candidate-side evaluation with pairwise)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(record, ensure_ascii=False) for record in report["case_records"]]
    p.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return p


def report_to_dict(report: dict) -> dict[str, Any]:
    """Return a JSON-safe dict for programmatic consumers."""
    return report
