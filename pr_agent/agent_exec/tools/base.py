"""Compatibility shim: tool primitives moved to ``agentguard.analysis.tools.base``."""

from agentguard.analysis.tools.base import (
    MCPToolAdapter,
    MCPToolDescriptor,
    Tool,
    ToolRegistry,
    default_registry,
    to_mcp_descriptor,
)

__all__ = [
    "MCPToolAdapter",
    "MCPToolDescriptor",
    "Tool",
    "ToolRegistry",
    "default_registry",
    "to_mcp_descriptor",
]
