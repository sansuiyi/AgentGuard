"""Read-only tools available to analysis agents."""

from agentguard.analysis.tools.base import (
    MCPToolAdapter,
    MCPToolDescriptor,
    Tool,
    ToolRegistry,
    default_registry,
    to_mcp_descriptor,
)
from agentguard.analysis.tools.find_references import FindReferencesTool
from agentguard.analysis.tools.read_file import ReadFileContextTool, extract_line_window
from agentguard.analysis.tools.static_analysis import RunStaticAnalysisTool
from agentguard.analysis.tools.workspace_read import WORKSPACE_TOOL_NAME, build_workspace_tool

__all__ = [
    "FindReferencesTool",
    "MCPToolAdapter",
    "MCPToolDescriptor",
    "ReadFileContextTool",
    "RunStaticAnalysisTool",
    "Tool",
    "ToolRegistry",
    "WORKSPACE_TOOL_NAME",
    "build_workspace_tool",
    "default_registry",
    "extract_line_window",
    "to_mcp_descriptor",
]
