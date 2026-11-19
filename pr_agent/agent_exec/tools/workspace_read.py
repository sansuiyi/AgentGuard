"""Compatibility shim: moved to ``agentguard.analysis.tools.workspace_read``."""

from agentguard.analysis.tools.workspace_read import (
    WORKSPACE_TOOL_NAME,
    WorkspaceReader,
    build_workspace_tool,
)

__all__ = ["WORKSPACE_TOOL_NAME", "WorkspaceReader", "build_workspace_tool"]
