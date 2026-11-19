"""Shared registries for the behavior-testing platform.

These are single sources of truth: the dataset validator rejects any assertion
type or capability that is not registered here, so a typo in a JSONL case fails
loudly instead of silently passing.
"""

from __future__ import annotations

# All rule-assertion types supported by the deterministic evaluator (§8.1).
ASSERTION_TYPES: frozenset[str] = frozenset(
    {
        "response_contains",
        "response_contains_any",
        "response_not_contains",
        "memory_contains",
        "memory_not_contains",
        "emotion_state_equals",
        "emotion_state_in",
        "emotion_transition",
        "tool_called",
        "tool_not_called",
        "tool_args_match",
        "tool_status_equals",
        "response_matches_tool_result",
        "latency_below",
    }
)

# Capability names referenced by ``expected_capabilities`` (must exist in
# ``configs/capability_mapping.yaml``).
CAPABILITIES: frozenset[str] = frozenset(
    {
        "long_term_memory",
        "emotion_response",
        "personality",
        "safety",
        "tool_state",
    }
)

CATEGORY_NAMES: tuple[str, ...] = ("memory", "emotion", "personality", "safety", "tool_state")

PRIORITY_NAMES: frozenset[str] = frozenset({"P0", "P1", "P2", "P3"})
