"""Multi-subagent fan-out and merge for the AgentGuard agent loop.

A ``ReviewerFederation`` partitions the PR diff files into per-file batches and
runs one bounded :class:`~agentguard.orchestration.runner.ReviewAgentRunner` per batch
concurrently, capped by a semaphore so a large PR cannot hammer the LLM
provider. The per-file findings are then merged with deterministic
deduplication so the same issue reported by two sub-agents is published once.

The federation reuses the existing agent loop, so every sub-agent still honors
the harness budgets (step/tool), the whitelist, loop detection and the Jev
verification rule. Two additional federation-level guardrails apply:

- Failure isolation: a crashed sub-agent is logged and skipped, never fatal to
  the run; the remaining batches still contribute their findings.
- A shared global LLM-call budget (:class:`FederationBudget` enforced by
  :class:`BudgetedAgentLLM`): once exhausted, further calls degrade to a canned
  finalize decision so each sub-agent's loop winds down through its existing
  fallback path instead of crashing mid-review.

Whether the federation is used at all is an orchestration decision made by
deterministic code (:func:`should_use_federation`), never by the model. The
merger is intentionally simple and deterministic so the aggregate result is
replayable and unit-testable.
"""

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any, List, Optional

from loguru import logger

from agentguard.core.llm import AgentLLM
from agentguard.core.policy import FederationPolicy, load_federation_policy, load_policy
from agentguard.core.schemas import Finding, ToolResult
from agentguard.orchestration.nodes import format_findings
from agentguard.orchestration.runner import ReviewAgentRunner
from pr_agent.algo.ai_handlers.litellm_ai_handler import LiteLLMAIHandler

# Connective words that should not make two different findings look similar.
_TITLE_STOPWORDS = {
    "a",
    "an",
    "the",
    "of",
    "to",
    "in",
    "on",
    "for",
    "and",
    "or",
    "is",
    "are",
    "be",
    "with",
    "from",
    "by",
    "at",
    "as",
    "this",
    "that",
    "it",
    "issue",
    "risk",
}


def _normalize_title(title: str) -> str:
    """Lower-case, strip punctuation and collapse whitespace for comparison."""
    text = re.sub(r"[^\w\u4e00-\u9fff]+", " ", (title or "").lower())
    return re.sub(r"\s+", " ", text).strip()


def _title_tokens(title: str) -> set[str]:
    """Token set for title similarity.

    Splits camelCase/underscore identifiers into words; for CJK titles with no
    ASCII words, falls back to character bigrams so Chinese titles still compare.
    """
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", title or "")
    words = {w for w in re.findall(r"[a-z0-9]+", spaced.lower()) if w not in _TITLE_STOPWORDS}
    if words:
        return words
    compact = re.sub(r"\s+", "", _normalize_title(title))
    if not compact:
        return set()
    if len(compact) == 1:
        return {compact}
    return {compact[i : i + 2] for i in range(len(compact) - 1)}


def _titles_similar(a: str, b: str, threshold: float) -> bool:
    """Jaccard similarity over tokens, with containment as a strong signal."""
    norm_a, norm_b = _normalize_title(a), _normalize_title(b)
    if not norm_a or not norm_b:
        return False
    if norm_a == norm_b:
        return True
    # One title fully contained in the other ("NPE hazard" vs "NPE hazard in login").
    if norm_a in norm_b or norm_b in norm_a:
        return True
    tokens_a, tokens_b = _title_tokens(a), _title_tokens(b)
    if not tokens_a or not tokens_b:
        return False
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union) >= threshold


def _is_duplicate(a: Finding, b: Finding, policy: FederationPolicy) -> bool:
    """Same file, same risk, within the line window, and similar title.

    The title must never need to match exactly: two sub-agents may phrase the
    same defect differently. Location proximity is the primary signal and title
    similarity guards against merging distinct issues on adjacent lines.
    """
    if (a.file_path or "").strip().lower() != (b.file_path or "").strip().lower():
        return False
    if a.risk_level != b.risk_level:
        return False
    if a.line_number is not None and b.line_number is not None:
        if abs(a.line_number - b.line_number) > policy.dedup_line_window:
            return False
    return _titles_similar(a.title, b.title, policy.dedup_title_threshold)


def _merge_pair(kept: Finding, incoming: Finding) -> Finding:
    """Fold ``incoming`` into ``kept`` without losing verification work."""
    updates: dict[str, Any] = {}
    if kept.verified is None and incoming.verified is not None:
        updates["verified"] = incoming.verified
        updates["verification_note"] = incoming.verification_note or kept.verification_note
    if len(incoming.description or "") > len(kept.description or ""):
        updates["description"] = incoming.description
    return kept.model_copy(update=updates) if updates else kept


def merge_findings(
    per_batch: List[List[Finding]], policy: Optional[FederationPolicy] = None
) -> List[Finding]:
    """Merge per-subagent findings with location-aware, semantic dedup.

    Two findings are the same issue when they target the same file and risk
    level, are within ``dedup_line_window`` lines, and their titles are similar
    (token overlap or containment) - never an exact title match. The first
    occurrence is kept, absorbing any verification verdict and the richer
    description from later duplicates. Order follows batch order then in-batch
    order, so the merged list stays deterministic and replayable.
    """
    policy = policy or load_federation_policy()
    merged: List[Finding] = []
    for batch in per_batch:
        for finding in batch:
            match_index = next(
                (i for i, kept in enumerate(merged) if _is_duplicate(kept, finding, policy)),
                None,
            )
            if match_index is None:
                merged.append(finding)
            else:
                merged[match_index] = _merge_pair(merged[match_index], finding)
    return merged


def partition_files(diff_files: List[Any], max_files_per_batch: int = 1) -> List[List[Any]]:
    """Partition diff files into batches. Defaults to one batch per file."""
    if max_files_per_batch < 1:
        max_files_per_batch = 1
    return [diff_files[i : i + max_files_per_batch] for i in range(0, len(diff_files), max_files_per_batch)]


class FederationBudget:
    """Shared, cooperative counter capping real LLM calls across sub-agents.

    Asyncio runs the sub-agents on one event loop, so plain integer mutation is
    safe without locking.
    """

    def __init__(self, max_calls: int) -> None:
        self.max_calls = max(0, max_calls)
        self.used = 0

    def try_consume(self) -> bool:
        """Take one call from the budget; False once the cap is reached."""
        if self.used >= self.max_calls:
            return False
        self.used += 1
        return True


class BudgetedAgentLLM(AgentLLM):
    """AgentLLM that stops issuing real calls once the shared budget is exhausted.

    On exhaustion it returns a canned finalize decision, so the sub-agent's loop
    degrades gracefully through its existing fallback path (finalize -> Jev ->
    loop detection) instead of crashing mid-review.
    """

    def __init__(
        self,
        budget: FederationBudget,
        ai_handler_factory=LiteLLMAIHandler,
        model: Optional[str] = None,
        handler: Any = None,
    ) -> None:
        super().__init__(ai_handler_factory=ai_handler_factory, model=model, handler=handler)
        self._budget = budget

    def with_model(self, model: Optional[str]) -> AgentLLM:
        """Select a different model for the verify pass while sharing the budget."""
        if not model or model == self.model_name():
            return self
        return BudgetedAgentLLM(
            self._budget, ai_handler_factory=self._factory, model=model, handler=self._handler
        )

    async def complete(self, system: str, user: str, temperature: float = 0.2) -> tuple[str, Any]:
        if not self._budget.try_consume():
            content = json.dumps(
                {
                    "action": "finalize",
                    "confidence": 0.0,
                    "reasoning": "global federation LLM budget exhausted",
                }
            )
            return content, "stop"
        return await super().complete(system, user, temperature)


class ReviewerFederation:
    """Fan out one agent per file batch and merge the findings."""

    def __init__(self, runner_factory=None, policy: Optional[FederationPolicy] = None) -> None:
        # Default to the production ReviewAgentRunner; tests inject a stub.
        self._runner_factory = runner_factory or ReviewAgentRunner
        self._policy = policy or load_federation_policy()
        # The production path shares one global LLM budget across sub-agents;
        # injected stub factories (tests) are left untouched.
        self._use_budgeted_llm = self._runner_factory is ReviewAgentRunner

    def _make_runner(self, budget: FederationBudget) -> Any:
        if self._use_budgeted_llm:
            # Configured review model applies here too; the runner derives the
            # verify model from the same settings and shares the budget.
            return ReviewAgentRunner(
                llm=BudgetedAgentLLM(budget, model=load_policy().review_model or None)
            )
        return self._runner_factory()

    async def _run_states(self, batches: List[List[Any]]) -> List[Any]:
        """Run one sub-agent per batch under the concurrency cap; never raises.

        Individual batch failures are logged and skipped (failure isolation),
        so callers must filter out ``BaseException`` entries.
        """
        semaphore = asyncio.Semaphore(max(1, self._policy.max_concurrency))
        budget = FederationBudget(self._policy.max_total_llm_calls)

        async def _run_batch(batch: List[Any]) -> Any:
            async with semaphore:
                runner = self._make_runner(budget)
                return await runner.run(batch)

        states = await asyncio.gather(*[_run_batch(b) for b in batches], return_exceptions=True)
        for batch, state in zip(batches, states, strict=True):
            if isinstance(state, BaseException):
                names = ", ".join(getattr(f, "filename", "?") for f in batch) or "?"
                logger.warning("federation sub-agent failed for batch [{}]: {!r}", names, state)
        return states

    async def review(
        self, diff_files: List[Any], max_files_per_batch: Optional[int] = None
    ) -> List[Finding]:
        """Run sub-agents concurrently and return the merged findings."""
        if not diff_files:
            return []
        batch_size = (
            max_files_per_batch
            if max_files_per_batch is not None
            else self._policy.max_files_per_batch
        )
        batches = partition_files(diff_files, max_files_per_batch=batch_size)
        states = await self._run_states(batches)
        per_batch_findings = [
            list(getattr(s, "findings", []) or [])
            for s in states
            if not isinstance(s, BaseException)
        ]
        return merge_findings(per_batch_findings)


# Aggregate audit/trajectory across sub-agents, for callers that want them.
async def review_with_audit(
    diff_files: List[Any],
    runner_factory=None,
    max_files_per_batch: Optional[int] = None,
):
    """Run the federation and return (findings, audit_events, trajectories, tool_results)."""
    if not diff_files:
        return [], [], [], []
    policy = load_federation_policy()
    federation = ReviewerFederation(runner_factory=runner_factory, policy=policy)
    batch_size = (
        max_files_per_batch if max_files_per_batch is not None else policy.max_files_per_batch
    )
    batches = partition_files(diff_files, max_files_per_batch=batch_size)
    states = await federation._run_states(batches)

    per_batch_findings = [
        list(getattr(s, "findings", []) or []) for s in states if not isinstance(s, BaseException)
    ]
    findings = merge_findings(per_batch_findings)
    audit_events: List[Any] = []
    trajectories: List[Any] = []
    tool_results: List[ToolResult] = []
    for s in states:
        if isinstance(s, BaseException):
            continue
        audit_events.extend(getattr(s, "audit_events", []) or [])
        trajectories.extend(getattr(s, "trajectory", []) or [])
        tool_results.extend(getattr(s, "tool_results", []) or [])
    return findings, audit_events, trajectories, tool_results


def should_use_federation(num_files: int, policy: Optional[FederationPolicy] = None) -> bool:
    """File-count-only predicate (kept for simple callers and tests).

    The authoritative orchestration decision is :func:`evaluate_federation`,
    which also considers the estimated diff size.
    """
    policy = policy or load_federation_policy()
    return bool(policy.enabled) and num_files >= policy.min_files


# Coarse chars-per-token heuristic for deciding whether the diff is too large
# for a single loop; exact counting is unnecessary for an orchestration gate.
_CHARS_PER_TOKEN = 4


def estimate_diff_tokens(diff_files: List[Any]) -> int:
    """Estimate the total diff size in tokens (~4 chars per token)."""
    total_chars = sum(len(getattr(f, "patch", "") or "") for f in diff_files)
    return total_chars // _CHARS_PER_TOKEN


@dataclass(frozen=True)
class FederationDecision:
    """Orchestration decision plus the human-readable judgment basis."""

    use_federation: bool
    num_files: int
    estimated_tokens: int
    reasons: List[str]


def evaluate_federation(
    diff_files: List[Any], policy: Optional[FederationPolicy] = None
) -> FederationDecision:
    """Decide (deterministic code, never the model) whether to fan out.

    Fan out when the federation is enabled AND the PR exceeds one of two
    thresholds: file count (many files to cover) or estimated diff tokens
    (one loop's budget cannot cover a single huge file). Every reason is
    recorded so the decision is auditable from the logs.
    """
    policy = policy or load_federation_policy()
    num_files = len(diff_files)
    estimated_tokens = estimate_diff_tokens(diff_files)
    reasons: List[str] = []

    if not policy.enabled:
        reasons.append("federation_enabled=false (single runner)")
    else:
        if num_files >= policy.min_files:
            reasons.append(f"files={num_files} >= federation_min_files={policy.min_files}")
        else:
            reasons.append(f"files={num_files} < federation_min_files={policy.min_files}")
        if estimated_tokens >= policy.min_diff_tokens:
            reasons.append(
                f"estimated_diff_tokens~{estimated_tokens} "
                f">= federation_min_diff_tokens={policy.min_diff_tokens}"
            )
        else:
            reasons.append(
                f"estimated_diff_tokens~{estimated_tokens} "
                f"< federation_min_diff_tokens={policy.min_diff_tokens}"
            )

    use = policy.enabled and (
        num_files >= policy.min_files or estimated_tokens >= policy.min_diff_tokens
    )
    return FederationDecision(
        use_federation=use, num_files=num_files, estimated_tokens=estimated_tokens, reasons=reasons
    )


async def run_federation_review(
    diff_files: List[Any], policy: Optional[FederationPolicy] = None
) -> tuple[str, List[Finding]]:
    """Orchestration entry point: fan out, merge, and format the final report.

    Returns ``(final_answer_text, merged_findings)`` ready for publication.
    """
    policy = policy or load_federation_policy()
    federation = ReviewerFederation(policy=policy)
    findings = await federation.review(diff_files)
    return format_findings(findings), findings
