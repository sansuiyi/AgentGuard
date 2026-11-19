"""Compatibility shim: federation moved to ``agentguard.orchestration.federation``."""

from agentguard.orchestration.federation import (
    BudgetedAgentLLM,
    FederationBudget,
    FederationDecision,
    ReviewerFederation,
    estimate_diff_tokens,
    evaluate_federation,
    load_federation_policy,
    merge_findings,
    partition_files,
    review_with_audit,
    run_federation_review,
    should_use_federation,
)

__all__ = [
    "BudgetedAgentLLM",
    "FederationBudget",
    "FederationDecision",
    "ReviewerFederation",
    "estimate_diff_tokens",
    "evaluate_federation",
    "load_federation_policy",
    "merge_findings",
    "partition_files",
    "review_with_audit",
    "run_federation_review",
    "should_use_federation",
]
