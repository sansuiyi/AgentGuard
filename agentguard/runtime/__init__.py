"""Dual-version execution engine: adapter, demo agent, fault injection, trace."""

from agentguard.runtime.adapter import AgentAdapter, InvokeResult
from agentguard.runtime.demo_agent import ALL_FAULT_IDS, DemoAgent
from agentguard.runtime.fault_injection import load_scenarios, resolve_fault_ids
from agentguard.runtime.version_runner import VersionRunner

__all__ = [
    "ALL_FAULT_IDS",
    "AgentAdapter",
    "DemoAgent",
    "InvokeResult",
    "VersionRunner",
    "load_scenarios",
    "resolve_fault_ids",
]
