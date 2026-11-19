"""Unit tests for the deterministic rule evaluator."""

from __future__ import annotations

from agentguard.core.enums import Version
from agentguard.core.models import AgentTrace, Assertion, StateSnapshot, TurnTrace
from agentguard.evaluation.rule_evaluator import RuleEvaluator


def _trace(
    response: str = "你好，我是小守。",
    memory: dict | None = None,
    emotion: str | None = "neutral",
    tool_calls: list | None = None,
    latency_ms: float = 1.0,
    extra_turns: list[TurnTrace] | None = None,
) -> AgentTrace:
    turns = [
        TurnTrace(
            turn_index=0,
            user_input="hi",
            agent_response=response,
            tool_calls=tool_calls or [],
            state_after=StateSnapshot(mood=emotion),
            latency_ms=latency_ms,
        )
    ]
    if extra_turns:
        turns.extend(extra_turns)
    return AgentTrace(
        trace_id="t1",
        run_id="r1",
        case_id="C1",
        version=Version.BASE,
        turns=turns,
        final_memory=memory or {},
        final_emotion=emotion,
    )


def _eval(trace: AgentTrace, assertion: Assertion) -> bool:
    return RuleEvaluator().evaluate(trace, [assertion])[0].passed


def test_response_contains() -> None:
    assert _eval(_trace(response="你好，我是小守。"), Assertion(type="response_contains", text="小守"))


def test_response_contains_any() -> None:
    assert _eval(_trace(response="太好了"), Assertion(type="response_contains_any", values=["开心", "太好了"]))


def test_response_not_contains() -> None:
    assert _eval(_trace(response="好的"), Assertion(type="response_not_contains", values=["已成功"]))


def test_memory_contains_and_not_contains() -> None:
    t = _trace(memory={"location": "苏州"})
    assert _eval(t, Assertion(type="memory_contains", key="location", value="苏州"))
    assert _eval(t, Assertion(type="memory_not_contains", key="password"))


def test_emotion_state_equals_and_in() -> None:
    t = _trace(emotion="sad")
    assert _eval(t, Assertion(type="emotion_state_equals", value="sad"))
    assert _eval(t, Assertion(type="emotion_state_in", values=["sad", "negative"]))


def test_emotion_transition() -> None:
    t = _trace(
        emotion="happy",
        extra_turns=[
            TurnTrace(
                turn_index=1,
                user_input="x",
                agent_response="y",
                state_after=StateSnapshot(mood="happy"),
            )
        ],
    )
    # first turn state_after.mood is the initial emotion for transition checks
    t.turns[0].state_after.mood = "anxious"
    assert _eval(t, Assertion(type="emotion_transition", from_value="anxious", to_values=["happy", "calm"]))
    assert _eval(t, Assertion(type="emotion_transition", direction="more_positive"))


def test_tool_assertions() -> None:
    from agentguard.core.models import ToolCall

    t = _trace(
        response="根据查询结果，明天 10:00 有日程：产品评审会。",
        tool_calls=[
            ToolCall(
                tool_name="query_schedule",
                arguments={"date": "明天"},
                status="completed",
                result="明天 10:00 有日程：产品评审会",
            )
        ],
    )
    assert _eval(t, Assertion(type="tool_called", tool_name="query_schedule"))
    assert _eval(t, Assertion(type="tool_args_match", tool_name="query_schedule", args={"date": "明天"}))
    assert _eval(t, Assertion(type="tool_status_equals", tool_name="query_schedule", status="completed"))
    assert _eval(t, Assertion(type="response_matches_tool_result", tool_name="query_schedule"))
    assert _eval(t, Assertion(type="tool_not_called", tool_name="delete_all_data"))


def test_latency_below() -> None:
    assert _eval(_trace(latency_ms=3.0), Assertion(type="latency_below", max_ms=10.0))
    assert not _eval(_trace(latency_ms=20.0), Assertion(type="latency_below", max_ms=10.0))
