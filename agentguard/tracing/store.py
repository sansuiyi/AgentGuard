"""Trace persistence: write each case/version trace to its own JSON file."""

from __future__ import annotations

import json
from pathlib import Path

from agentguard.core.models import AgentTrace


def trace_filename(trace: AgentTrace) -> str:
    return f"{trace.case_id}.{trace.version.value}.json"


class TraceStore:
    """Saves traces under a per-run ``traces/`` directory."""

    def __init__(self, traces_dir: str | Path) -> None:
        self._dir = Path(traces_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def save(self, trace: AgentTrace) -> Path:
        path = self._dir / trace_filename(trace)
        path.write_text(
            json.dumps(trace.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path
