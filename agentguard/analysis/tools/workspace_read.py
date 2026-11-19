"""Read-only workspace lookup exposed as an MCP-standardized tool.

The built-in tools only see the PR diff, so the agent cannot inspect unchanged
source such as a type definition or an interface declaration that the change
depends on. This tool breaks that "closed world" through the MCP extension
point: it is adapted with :class:`MCPToolAdapter` and therefore obeys the same
whitelist, timeout, budget and audit rules as every other tool.

Safety posture (read-only by construction):

- the root is an explicit directory; every resolved path must stay inside it,
- absolute paths and ``..`` traversal are refused,
- only allow-listed source extensions are readable,
- oversized files and oversized result sets are refused/truncated,
- directories such as ``.git`` and ``node_modules`` are never scanned.
"""

import asyncio
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from agentguard.analysis.tools.base import MCPToolAdapter
from agentguard.core.policy import WorkspacePolicy, load_workspace_policy
from agentguard.core.schemas import ToolResult, ToolStatus

WORKSPACE_TOOL_NAME = "read_workspace_source"

_SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    "build",
    "dist",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
}

_INPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": "Repository-relative path of a source file to read (read-only).",
        },
        "symbol": {
            "type": "string",
            "description": "Exact text to search for across the workspace (e.g. a class or function name).",
        },
        "line_start": {"type": "integer", "description": "Optional first line to return (1-based)."},
        "line_end": {"type": "integer", "description": "Optional last line to return (1-based)."},
    },
    "additionalProperties": False,
}


def _resolve_inside(root: Path, raw_path: str) -> Optional[Path]:
    """Resolve a repository-relative path, refusing anything outside the root."""
    if not raw_path or os.path.isabs(raw_path):
        return None
    candidate = (root / raw_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None  # traversal escaped the root
    if not candidate.is_file():
        return None
    return candidate


def _is_allowed(path: Path, extensions: List[str]) -> bool:
    return path.suffix.lower() in extensions


class WorkspaceReader:
    """Deterministic read-only file reader and symbol scanner."""

    def __init__(self, root: Path, policy: WorkspacePolicy) -> None:
        self._root = root
        self._policy = policy

    async def execute(self, arguments: Dict[str, Any]) -> ToolResult:
        # Offload the blocking filesystem walk so concurrent federation
        # sub-agents are not serialized behind one another.
        return await asyncio.to_thread(self._execute_sync, arguments)

    def _execute_sync(self, arguments: Dict[str, Any]) -> ToolResult:
        symbol = arguments.get("symbol")
        raw_path = arguments.get("path")
        if not symbol and not raw_path:
            return self._unsupported("provide either 'path' or 'symbol'")
        if symbol and raw_path:
            return self._unsupported("provide only one of 'path' or 'symbol'")
        if symbol:
            return self._search_symbol(str(symbol))
        return self._read_file(str(raw_path), arguments.get("line_start"), arguments.get("line_end"))

    def _read_file(
        self, raw_path: str, line_start: Optional[int], line_end: Optional[int]
    ) -> ToolResult:
        path = _resolve_inside(self._root, raw_path)
        if path is None:
            return self._unsupported(f"path is outside the workspace root or does not exist: {raw_path}")
        if not _is_allowed(path, self._policy.allowed_extensions):
            return self._unsupported(f"file type not readable: {path.suffix or '(none)'}")
        size = path.stat().st_size
        if size > self._policy.max_file_bytes:
            return self._unsupported(
                f"file too large ({size} bytes > {self._policy.max_file_bytes}); "
                "use 'symbol' to locate the relevant lines"
            )

        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        total = len(lines)
        start = max(1, int(line_start or 1))
        end = min(total, int(line_end or total))
        selected = [
            {"line": number, "text": lines[number - 1]}
            for number in range(start, end + 1)
            if number <= total
        ]
        return ToolResult(
            tool_name=WORKSPACE_TOOL_NAME,
            success=True,
            status=ToolStatus.COMPLETED,
            data={
                "path": path.relative_to(self._root).as_posix(),
                "total_lines": total,
                "line_start": start,
                "line_end": end,
                "lines": selected,
            },
        )

    def _search_symbol(self, symbol: str) -> ToolResult:
        matches: List[Dict[str, Any]] = []
        scanned = 0
        truncated = False

        for current, dirnames, filenames in os.walk(self._root):
            dirnames[:] = sorted(d for d in dirnames if d not in _SKIP_DIRS)
            for filename in sorted(filenames):
                if scanned >= self._policy.max_scan_files:
                    truncated = True
                    break
                path = Path(current) / filename
                if not _is_allowed(path, self._policy.allowed_extensions):
                    continue
                try:
                    if path.stat().st_size > self._policy.max_file_bytes:
                        continue
                    text = path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                scanned += 1
                for number, line in enumerate(text.splitlines(), start=1):
                    if symbol in line:
                        matches.append(
                            {
                                "path": path.relative_to(self._root).as_posix(),
                                "line": number,
                                "text": line.strip()[:300],
                            }
                        )
                        if len(matches) >= self._policy.max_matches:
                            truncated = True
                            break
                if truncated:
                    break
            if truncated:
                break

        return ToolResult(
            tool_name=WORKSPACE_TOOL_NAME,
            success=True,
            status=ToolStatus.COMPLETED,
            data={
                "symbol": symbol,
                "matches": matches,
                "count": len(matches),
                "files_scanned": scanned,
                "truncated": truncated,
            },
        )

    def _unsupported(self, error: str) -> ToolResult:
        return ToolResult(
            tool_name=WORKSPACE_TOOL_NAME,
            success=False,
            status=ToolStatus.UNSUPPORTED,
            error=error,
        )


def build_workspace_tool(policy: Optional[WorkspacePolicy] = None):
    """Return the workspace read-only MCP tool, or None when disabled.

    Registration goes through :class:`MCPToolAdapter`, so the tool is
    whitelisted, schema-validated, timeout-bounded, budget-counted and audited
    exactly like the built-in tools.
    """
    policy = policy or load_workspace_policy()
    if not policy.enabled or not policy.root:
        return None
    root = Path(policy.root).expanduser().resolve()
    if not root.is_dir():
        return None
    reader = WorkspaceReader(root, policy)
    return MCPToolAdapter(
        name=WORKSPACE_TOOL_NAME,
        description=(
            "Read-only lookup of unchanged workspace source: read a file by "
            "repository-relative path, or search an exact symbol name to find "
            "its type/interface/function declaration."
        ),
        input_schema=_INPUT_SCHEMA,
        handler=reader.execute,
    )
