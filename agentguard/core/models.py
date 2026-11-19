"""Pydantic data models for the AgentGuard behavior-testing platform.

Field names use snake_case throughout and every model forbids extra keys so
schema drift in the golden dataset is caught at load/validate time rather than
deep inside evaluation. These models are unrelated to the review-loop models in
``agentguard.core.schemas``.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from agentguard.core.enums import CaseStatus, Category, DecisionStatus, Priority, Version


class Fact(BaseModel):
    """A single user fact seeded into the agent's memory before a run."""

    model_config = ConfigDict(extra="forbid")

    key: str
    value: Any
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class UserProfile(BaseModel):
    """Fictional user state shared by both versions of a run."""

    model_config = ConfigDict(extra="forbid")

    user_id: str
    facts: list[Fact] = Field(default_factory=list)


class Assertion(BaseModel):
    """One machine-checkable expectation. ``type`` names an entry in the registry."""

    model_config = ConfigDict(extra="forbid")

    type: str
    turn_index: Optional[int] = None
    key: Optional[str] = None
    value: Optional[Any] = None
    values: Optional[list[Any]] = None
    text: Optional[str] = None
    tool_name: Optional[str] = None
    args: Optional[dict[str, Any]] = None
    status: Optional[str] = None
    max_ms: Optional[float] = None
    from_value: Optional[str] = None
    to_values: Optional[list[str]] = None
    direction: Optional[str] = None


class TurnExpectation(BaseModel):
    """Per-turn expectations. Informational shorthand; the canonical contract is ``assertions``."""

    model_config = ConfigDict(extra="forbid")

    memory_write_contains: Optional[list[str]] = None
    response_contains_any: Optional[list[str]] = None
    response_contains: Optional[str] = None
    tool_called: Optional[str] = None
    emotion_state: Optional[str] = None


class Turn(BaseModel):
    """One conversation turn."""

    model_config = ConfigDict(extra="forbid")

    input: str
    expected: Optional[TurnExpectation] = None


class JudgeRubric(BaseModel):
    """Optional LLM-judge rubric; never blocks the deterministic path."""

    model_config = ConfigDict(extra="forbid")

    question: str
    pass_threshold: int = Field(default=4, ge=1)
    dimensions: list[str] = Field(default_factory=list)


class TestCase(BaseModel):
    """A golden test case."""

    model_config = ConfigDict(extra="forbid")
    # Prevent pytest from attempting to collect this model as a test class.
    __test__ = False

    case_id: str
    title: str
    category: Category
    tags: list[str] = Field(default_factory=list)
    priority: Priority = Priority.P2
    description: str = ""
    user_profile: UserProfile
    turns: list[Turn] = Field(min_length=1)
    assertions: list[Assertion] = Field(min_length=1)
    judge_rubric: Optional[JudgeRubric] = None
    expected_capabilities: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("case_id")
    @classmethod
    def _nonempty_case_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("case_id must not be empty")
        return value


class MemoryOp(BaseModel):
    """A single memory read/write/delete event."""

    model_config = ConfigDict(extra="forbid")

    key: str
    value: Any = None
    operation: str = "write"  # read | write | delete


class ToolCall(BaseModel):
    """A single tool invocation captured from the agent."""

    model_config = ConfigDict(extra="forbid")

    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    status: str = "completed"  # completed | failed | timeout | refused
    result: Any = None
    error: Optional[str] = None


class StateSnapshot(BaseModel):
    """Structured agent state at a point in time."""

    model_config = ConfigDict(extra="forbid")

    mood: Optional[str] = None
    memory_keys: list[str] = Field(default_factory=list)


class TurnTrace(BaseModel):
    """Trace for one turn of one version."""

    model_config = ConfigDict(extra="forbid")

    turn_index: int
    user_input: str
    agent_response: str
    memory_reads: list[MemoryOp] = Field(default_factory=list)
    memory_writes: list[MemoryOp] = Field(default_factory=list)
    tool_calls: list[ToolCall] = Field(default_factory=list)
    state_before: StateSnapshot = Field(default_factory=StateSnapshot)
    state_after: StateSnapshot = Field(default_factory=StateSnapshot)
    latency_ms: float = 0.0


class AgentTrace(BaseModel):
    """Full trace for one case/version pair."""

    model_config = ConfigDict(extra="forbid")

    trace_id: str
    run_id: str
    case_id: str
    version: Version
    turns: list[TurnTrace] = Field(default_factory=list)
    status: str = "success"  # success | error | timeout
    error: Optional[str] = None
    final_memory: dict[str, Any] = Field(default_factory=dict)
    final_emotion: Optional[str] = None


class RuleResult(BaseModel):
    """Outcome of a single assertion evaluated against a trace."""

    model_config = ConfigDict(extra="forbid")

    assertion: str
    passed: bool
    actual: Optional[str] = None
    expected: Optional[str] = None
    evidence: Optional[str] = None


class JudgeResult(BaseModel):
    """Optional LLM-judge result. ``status`` is ``unavailable`` when no model is configured."""

    model_config = ConfigDict(extra="forbid")

    score: int = 0
    passed: Optional[bool] = None
    reason: str = ""
    evidence: str = ""
    status: str = "unavailable"  # available | unavailable | error


class PairwiseResult(BaseModel):
    """Base-vs-candidate comparison for one case."""

    model_config = ConfigDict(extra="forbid")

    regressed: bool = False
    summary: str = ""
    base_passed: bool = False
    candidate_passed: bool = False


class EvaluationResult(BaseModel):
    """Aggregated evaluation for one case/version pair."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    version: Version
    rule_results: list[RuleResult] = Field(default_factory=list)
    judge_result: Optional[JudgeResult] = None
    absolute_score: float = 0.0
    pairwise_result: Optional[PairwiseResult] = None
    status: CaseStatus = CaseStatus.PASS


class RiskDecision(BaseModel):
    """Final deterministic merge-gate decision."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    decision: DecisionStatus
    decision_reason: str
    evidence_refs: list[str] = Field(default_factory=list)
    policy_version: str = "1.0.0"
    timestamp: str = ""
    p0_count: int = 0
    p1_count: int = 0
    warnings: list[str] = Field(default_factory=list)
