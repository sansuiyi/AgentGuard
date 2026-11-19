"""Read the changed-file context of a PR diff.

Reuses the existing GitProvider ``get_diff_files`` result rather than inventing
a second data path. It returns the changed fragments with line numbers and, when
available, the surrounding file content; it never treats a deleted line as the
current version of the file.

When a ``line_number`` is supplied it returns a window of real source lines
around that line (``context_lines`` before and after), which is what the
independent verification pass needs: the verifier must see the code, not just a
prose description of it. The window is taken from the full head-file content
when the provider supplied it, and otherwise reconstructed from the unified
diff hunks (which only carry the changed regions plus their local context).
"""

import re
from typing import Any, Dict, List, Optional

from agentguard.core.schemas import ToolResult, ToolStatus

_HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def _new_file_lines_from_patch(patch: str) -> Dict[int, str]:
    """Map new-file line numbers to content by parsing unified diff hunks.

    Deleted (``-``) lines are skipped: they are not part of the current file.
    """
    lines: Dict[int, str] = {}
    new_line: Optional[int] = None
    for raw in (patch or "").splitlines():
        header = _HUNK_HEADER.match(raw)
        if header:
            new_line = int(header.group(3))
            continue
        if new_line is None or not raw or raw.startswith("\\"):
            # Before the first hunk there is only file metadata; "\ No newline"
            # markers carry no content.
            continue
        marker, text = raw[0], raw[1:]
        if marker == "-":
            continue  # deleted line: not current content
        if marker in ("+", " "):
            lines[new_line] = text
            new_line += 1
    return lines


def extract_line_window(
    file_patch: Any, line_number: Optional[int], context_lines: int
) -> Dict[str, Any]:
    """Return ``context_lines`` of real source around ``line_number``.

    Prefers the provider's full head-file content, falling back to the unified
    diff hunks. Returns an empty window when neither source is available.
    """
    window = max(1, context_lines)
    if line_number is None:
        return {"lines": [], "source": None, "file_path": getattr(file_patch, "filename", None)}

    source = None
    head_content = getattr(file_patch, "head_file", "") or ""
    head_lines = head_content.splitlines()
    # Use the provider's full new-file content only when it really is content:
    # it must not be the bare filename (some test doubles store the name there)
    # and it must be long enough to contain the requested line.
    if head_lines and head_content != getattr(file_patch, "filename", None) and len(head_lines) >= line_number:
        source_lines: Dict[int, str] = {i: text for i, text in enumerate(head_lines, start=1)}
        source = "head_file"
    else:
        source_lines = _new_file_lines_from_patch(getattr(file_patch, "patch", "") or "")
        source = "patch" if source_lines else None

    if not source_lines:
        return {"lines": [], "source": None, "file_path": getattr(file_patch, "filename", None)}

    start = max(1, line_number - window)
    end = line_number + window
    lines = [
        {"line": number, "text": source_lines[number], "is_target": number == line_number}
        for number in sorted(source_lines)
        if start <= number <= end
    ]
    return {
        "file_path": getattr(file_patch, "filename", None),
        "line_number": line_number,
        "context_lines": window,
        "source": source,
        "lines": lines,
    }


class ReadFileContextTool:
    name = "read_file_context"
    description = (
        "Return the changed fragments (with line numbers) of files in the PR diff, "
        "optionally restricted to a single file path. When line_number is provided, "
        "return context_lines of real source before and after that line."
    )
    # MCP-style self-description: a JSON Schema object describing the arguments.
    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Optional file path to restrict the returned diff fragments.",
            },
            "line_number": {
                "type": "integer",
                "description": "Optional 1-based line to center a source-context window on.",
            },
            "context_lines": {
                "type": "integer",
                "description": "Number of source lines to include before and after line_number.",
            },
        },
        "additionalProperties": False,
    }

    def __init__(self, files: list) -> None:
        # ``files`` is the list of FilePatchInfo already loaded by the caller.
        self._files = files

    async def execute(self, arguments: Dict[str, Any]) -> ToolResult:
        file_path = arguments.get("file_path")
        matched = self._files
        if file_path:
            matched = [f for f in self._files if f.filename == file_path]

        if not matched:
            return ToolResult(
                tool_name=self.name,
                success=False,
                status=ToolStatus.UNSUPPORTED,
                data={"files": []},
                error=f"no diff data available for {file_path or 'the PR'}",
            )

        line_number = arguments.get("line_number")
        if line_number is not None:
            windows: List[Dict[str, Any]] = [
                extract_line_window(f, line_number, int(arguments.get("context_lines") or 30))
                for f in matched
            ]
            windows = [w for w in windows if w.get("lines")]
            if windows:
                return ToolResult(
                    tool_name=self.name,
                    success=True,
                    status=ToolStatus.COMPLETED,
                    data={"context": windows},
                )
            # Fall through to the raw patch so the caller still gets evidence.

        entries = []
        for f in matched:
            entries.append(
                {
                    "filename": f.filename,
                    "edit_type": getattr(f.edit_type, "name", None),
                    "num_plus_lines": f.num_plus_lines,
                    "num_minus_lines": f.num_minus_lines,
                    # Raw unified diff; the consumer must not mistake '-' lines
                    # for the current file content.
                    "patch": f.patch,
                    "content_fetch_failed": getattr(f, "content_fetch_failed", False),
                }
            )

        return ToolResult(
            tool_name=self.name,
            success=True,
            status=ToolStatus.COMPLETED,
            data={"files": entries},
        )
