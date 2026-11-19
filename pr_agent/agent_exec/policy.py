"""Compatibility shim: budget policies moved to ``agentguard.core.policy``."""

from agentguard.core.policy import (
    AgentPolicy,
    FederationPolicy,
    WorkspacePolicy,
    load_federation_policy,
    load_policy,
    load_workspace_policy,
)

__all__ = [
    "AgentPolicy",
    "FederationPolicy",
    "WorkspacePolicy",
    "load_federation_policy",
    "load_policy",
    "load_workspace_policy",
]
