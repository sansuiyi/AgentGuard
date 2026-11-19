"""Tests for the read-only workspace MCP tool.

The tool exists to break the diff-only "closed world" while staying read-only:
it can read or search unchanged source, but never escapes the workspace root or
touches non-source files.
"""

import pytest

from agentguard.analysis.tools import WORKSPACE_TOOL_NAME, build_workspace_tool
from agentguard.core.policy import WorkspacePolicy
from agentguard.core.schemas import ToolStatus


def _policy(root, **overrides) -> WorkspacePolicy:
    return WorkspacePolicy(enabled=True, root=str(root), **overrides)


@pytest.fixture()
def workspace(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "models.py").write_text(
        "class User:\n    pass\n\n\ndef get_user(uid):\n    return User()\n", encoding="utf-8"
    )
    (tmp_path / "secret.txt").write_text("token=abc\n", encoding="utf-8")
    return tmp_path


def test_workspace_tool_disabled_by_default(tmp_path):
    assert build_workspace_tool(WorkspacePolicy(enabled=False, root=str(tmp_path))) is None
    assert build_workspace_tool(WorkspacePolicy(enabled=True, root="")) is None


def test_workspace_tool_is_registered_with_mcp_schema(workspace):
    tool = build_workspace_tool(_policy(workspace))
    assert tool is not None
    assert tool.name == WORKSPACE_TOOL_NAME
    assert tool.input_schema["additionalProperties"] is False
    assert set(tool.input_schema["properties"]) == {"path", "symbol", "line_start", "line_end"}


@pytest.mark.asyncio
async def test_workspace_tool_reads_unchanged_source(workspace):
    tool = build_workspace_tool(_policy(workspace))
    result = await tool.execute({"path": "pkg/models.py", "line_start": 1, "line_end": 2})
    assert result.status is ToolStatus.COMPLETED
    assert result.data["path"] == "pkg/models.py"
    assert [entry["text"] for entry in result.data["lines"]] == ["class User:", "    pass"]


@pytest.mark.asyncio
async def test_workspace_tool_finds_symbol_declarations(workspace):
    tool = build_workspace_tool(_policy(workspace))
    result = await tool.execute({"symbol": "get_user"})
    assert result.status is ToolStatus.COMPLETED
    assert result.data["count"] == 1
    assert result.data["matches"][0]["path"] == "pkg/models.py"
    assert result.data["matches"][0]["line"] == 5


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["../outside.py", "/etc/passwd", "pkg/../../../etc/hosts"])
async def test_workspace_tool_refuses_paths_outside_root(workspace, path):
    tool = build_workspace_tool(_policy(workspace))
    result = await tool.execute({"path": path})
    assert result.status is ToolStatus.UNSUPPORTED
    assert "outside the workspace root" in result.error


@pytest.mark.asyncio
async def test_workspace_tool_refuses_non_source_extensions(workspace):
    tool = build_workspace_tool(_policy(workspace))
    result = await tool.execute({"path": "secret.txt"})
    assert result.status is ToolStatus.UNSUPPORTED
    assert "file type not readable" in result.error


@pytest.mark.asyncio
async def test_workspace_tool_refuses_oversized_files(workspace):
    (workspace / "big.py").write_text("x = 1\n" * 2000, encoding="utf-8")
    tool = build_workspace_tool(_policy(workspace, max_file_bytes=100))
    result = await tool.execute({"path": "big.py"})
    assert result.status is ToolStatus.UNSUPPORTED
    assert "file too large" in result.error


@pytest.mark.asyncio
async def test_workspace_tool_requires_path_or_symbol(workspace):
    tool = build_workspace_tool(_policy(workspace))
    result = await tool.execute({})
    assert result.status is ToolStatus.UNSUPPORTED
    assert "either 'path' or 'symbol'" in result.error
