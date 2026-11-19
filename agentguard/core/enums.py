"""Enums shared across the AgentGuard behavior-testing platform.

These are deliberately separate from the review-loop enums in
``agentguard.core.schemas`` (which serve the OODA code-review agent) so the two
domains never share an ambiguous vocabulary.
"""

from enum import Enum


class Category(str, Enum):
    """The five behavior capabilities under test."""

    MEMORY = "memory"
    EMOTION = "emotion"
    PERSONALITY = "personality"
    SAFETY = "safety"
    TOOL_STATE = "tool_state"


class Priority(str, Enum):
    """Risk-criticality of a test case."""

    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class Version(str, Enum):
    """Which side of a dual-version comparison a trace belongs to."""

    BASE = "base"
    CANDIDATE = "candidate"


class DecisionStatus(str, Enum):
    """The only allowed final merge-gate states."""

    PASS = "PASS"
    REVIEW = "REVIEW"
    BLOCK = "BLOCK"
    ERROR = "ERROR"


class CaseStatus(str, Enum):
    """Per-case, per-version outcome."""

    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"
    SKIPPED = "skipped"


class SelectionMode(str, Enum):
    """Test-selection strategy."""

    FULL = "full"
    SMOKE = "smoke"
    IMPACT = "impact"
    RISK_BASED = "risk_based"


class EmotionState(str, Enum):
    """Coarse deterministic emotion vocabulary for the demo agent."""

    ANGRY = "angry"
    ANXIOUS = "anxious"
    SAD = "sad"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    CALM = "calm"
    HAPPY = "happy"
    POSITIVE = "positive"


# Valence ordering used by the ``emotion_transition`` assertion. Negative values
# are "worse" (higher distress), positive values are "better" (higher well-being).
EMOTION_VALENCE: dict[str, int] = {
    EmotionState.ANGRY: -2,
    EmotionState.ANXIOUS: -1,
    EmotionState.SAD: -1,
    EmotionState.NEGATIVE: -1,
    EmotionState.NEUTRAL: 0,
    EmotionState.CALM: 0,
    EmotionState.HAPPY: 1,
    EmotionState.POSITIVE: 1,
}
