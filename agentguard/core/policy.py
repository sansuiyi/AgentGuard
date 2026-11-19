"""Execution policy for the AgentGuard agent loop.

The harness reads these bounds from ``[agent_exec]`` settings (falling back to
conservative defaults) and enforces them in server code, independent of the
model's prompt. The model may *suggest* continuing, but the policy decides when
the loop must stop or when a tool call is refused.

Model selection is also policy: the first (review) pass and the independent
second (verify) pass may use different configured models, so upgrading the
verifier never requires a code change.
"""

from dataclasses import dataclass, field
from typing import List

from pr_agent.config_loader import get_settings


@dataclass(frozen=True)
class AgentPolicy:
    max_steps: int = 6
    max_tool_calls: int = 4
    max_tokens: int = 20000
    tool_timeout_seconds: float = 10.0
    # High-risk findings below this confidence threshold are flagged for
    # verification by the decision layer (Jev).
    verify_confidence_threshold: float = 0.6
    # Loop detection: if the last N decision signatures repeat, force finalize.
    loop_detection_window: int = 3
    # Harness: refuse tools that are not in the whitelist.
    enforce_tool_whitelist: bool = True
    # Model used for the first (review) pass; empty = config.model.
    review_model: str = ""
    # Model used for the independent (verify) pass; empty = review_model.
    verify_model: str = ""
    # Lines of real source context (before and after) handed to the verifier.
    verify_context_lines: int = 30


@dataclass(frozen=True)
class FederationPolicy:
    """Federation-level bounds for multi-subagent fan-out.

    These are orchestration decisions made by deterministic code (never the
    model) and are enforced by the harness, mirroring :class:`AgentPolicy`.
    """

    # Federation is a separate gate on top of the agent loop itself.
    enabled: bool = False
    # Below this file count a single runner is cheaper than fan-out.
    min_files: int = 4
    # Estimated diff tokens (~4 chars/token) at or above which one loop's
    # budget cannot reasonably cover the review, even for a single file.
    min_diff_tokens: int = 6000
    # Diff files per sub-agent batch (1 = one agent per file).
    max_files_per_batch: int = 1
    # Cap concurrent sub-agents so a large PR cannot hammer the LLM provider.
    max_concurrency: int = 3
    # Hard cap on real LLM calls across the whole federation run (all
    # sub-agents combined); exhausted sub-agents degrade to a canned finalize.
    max_total_llm_calls: int = 60
    # Dedup: findings on the same file within this many lines of each other
    # (and with similar titles) are treated as the same issue.
    dedup_line_window: int = 5
    # Dedup: title token-overlap (Jaccard) at or above this counts as similar.
    dedup_title_threshold: float = 0.5


@dataclass(frozen=True)
class WorkspacePolicy:
    """Read-only access to the workspace checkout for unchanged source lookup.

    Exposed as an MCP-standardized tool so the agent can find type definitions
    and interface declarations that the diff alone cannot show. Disabled by
    default; the root must be an explicit directory and every path stays inside it.
    """

    enabled: bool = False
    root: str = ""
    max_file_bytes: int = 262144
    max_matches: int = 50
    max_scan_files: int = 2000
    allowed_extensions: List[str] = field(
        default_factory=lambda: [
            ".py",
            ".pyi",
            ".ts",
            ".tsx",
            ".js",
            ".jsx",
            ".java",
            ".go",
            ".rs",
            ".md",
            ".toml",
            ".yaml",
            ".yml",
            ".json",
        ]
    )


def _agent_exec_settings() -> dict:
    return get_settings().get("agent_exec", {}) or {}


def _int(settings: dict, key: str, default: int) -> int:
    """Read an integer setting, falling back to ``default`` when malformed."""
    try:
        return int(settings.get(key, default))
    except (TypeError, ValueError):
        return default


def _float(settings: dict, key: str, default: float) -> float:
    """Read a float setting, falling back to ``default`` when malformed."""
    try:
        return float(settings.get(key, default))
    except (TypeError, ValueError):
        return default


def load_federation_policy() -> FederationPolicy:
    """Build a federation policy from ``[agent_exec]`` settings with safe defaults."""
    agent_exec = _agent_exec_settings()

    return FederationPolicy(
        enabled=bool(agent_exec.get("federation_enabled", FederationPolicy.enabled)),
        min_files=_int(agent_exec, "federation_min_files", FederationPolicy.min_files),
        min_diff_tokens=_int(agent_exec, "federation_min_diff_tokens", FederationPolicy.min_diff_tokens),
        max_files_per_batch=_int(
            agent_exec, "federation_max_files_per_batch", FederationPolicy.max_files_per_batch
        ),
        max_concurrency=_int(agent_exec, "federation_max_concurrency", FederationPolicy.max_concurrency),
        max_total_llm_calls=_int(
            agent_exec, "federation_max_total_llm_calls", FederationPolicy.max_total_llm_calls
        ),
        dedup_line_window=_int(
            agent_exec, "federation_dedup_line_window", FederationPolicy.dedup_line_window
        ),
        dedup_title_threshold=_float(
            agent_exec, "federation_dedup_title_threshold", FederationPolicy.dedup_title_threshold
        ),
    )


def load_workspace_policy() -> WorkspacePolicy:
    """Build the workspace read-only tool policy from ``[agent_exec]`` settings."""
    agent_exec = _agent_exec_settings()

    raw_extensions = agent_exec.get("workspace_allowed_extensions")
    if isinstance(raw_extensions, str):
        extensions = [e.strip() for e in raw_extensions.split(",") if e.strip()]
    elif isinstance(raw_extensions, (list, tuple)):
        extensions = [str(e).strip() for e in raw_extensions if str(e).strip()]
    else:
        extensions = list(WorkspacePolicy().allowed_extensions)

    return WorkspacePolicy(
        enabled=bool(agent_exec.get("workspace_mcp_enabled", WorkspacePolicy.enabled)),
        root=str(agent_exec.get("workspace_root", WorkspacePolicy.root) or ""),
        max_file_bytes=_int(agent_exec, "workspace_max_file_bytes", WorkspacePolicy.max_file_bytes),
        max_matches=_int(agent_exec, "workspace_max_matches", WorkspacePolicy.max_matches),
        max_scan_files=_int(agent_exec, "workspace_max_scan_files", WorkspacePolicy.max_scan_files),
        allowed_extensions=[e if e.startswith(".") else f".{e}" for e in extensions],
    )


def load_policy() -> AgentPolicy:
    """Build a policy from ``[agent_exec]`` settings with safe defaults."""
    agent_exec = _agent_exec_settings()

    return AgentPolicy(
        max_steps=_int(agent_exec, "max_steps", AgentPolicy.max_steps),
        max_tool_calls=_int(agent_exec, "max_tool_calls", AgentPolicy.max_tool_calls),
        max_tokens=_int(agent_exec, "max_tokens", AgentPolicy.max_tokens),
        tool_timeout_seconds=_float(agent_exec, "tool_timeout_seconds", AgentPolicy.tool_timeout_seconds),
        verify_confidence_threshold=_float(
            agent_exec, "verify_confidence_threshold", AgentPolicy.verify_confidence_threshold
        ),
        loop_detection_window=_int(
            agent_exec, "loop_detection_window", AgentPolicy.loop_detection_window
        ),
        enforce_tool_whitelist=bool(
            agent_exec.get("enforce_tool_whitelist", AgentPolicy.enforce_tool_whitelist)
        ),
        review_model=str(agent_exec.get("review_model", AgentPolicy.review_model) or ""),
        verify_model=str(agent_exec.get("verify_model", AgentPolicy.verify_model) or ""),
        verify_context_lines=_int(agent_exec, "verify_context_lines", AgentPolicy.verify_context_lines),
    )
