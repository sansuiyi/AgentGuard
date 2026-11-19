"""Compatibility shim: the runner moved to ``agentguard.orchestration.runner``."""

from agentguard.orchestration.runner import ReviewAgentRunner, is_enabled

__all__ = ["ReviewAgentRunner", "is_enabled"]
