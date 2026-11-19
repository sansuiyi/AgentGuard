"""Compatibility shim: tools moved to ``agentguard.analysis.tools``."""

from agentguard.analysis.tools import (
    WORKSPACE_TOOL_NAME,
    FindReferencesTool,
    MCPToolAdapter,
    MCPToolDescriptor,
    ReadFileContextTool,
    RunStaticAnalysisTool,
    Tool,
    ToolRegistry,
    build_workspace_tool,
    default_registry,
    extract_line_window,
    to_mcp_descriptor,
)

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
