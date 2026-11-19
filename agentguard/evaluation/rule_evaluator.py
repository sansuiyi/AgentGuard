"""Deterministic rule evaluator.

Every assertion type in ``agentguard.dataset.registry.ASSERTION_TYPES`` maps to a
pure function ``(trace, assertion) -> RuleResult``. An unknown type raises
``AssertionTypeError`` — it is a data error, never a silent pass.
"""

from __future__ import annotations

from typing import Callable

from agentguard.core.enums import EMOTION_VALENCE
from agentguard.core.errors import AssertionTypeError
from agentguard.core.models import AgentTrace, Assertion, RuleResult, ToolCall, TurnTrace


def _turns(trace: AgentTrace) -> list[TurnTrace]:
    return trace.turns


def _responses(trace: AgentTrace, turn_index: int | None = None) -> list[str]:
    turns = trace.turns if turn_index is None else [t for t in trace.turns if t.turn_index == turn_index]
    return [t.agent_response for t in turns]


def _tool_calls(trace: AgentTrace, tool_name: str | None = None) -> list[ToolCall]:
    calls: list[ToolCall] = []
    for turn in trace.turns:
        for call in turn.tool_calls:
            if tool_name is None or call.tool_name == tool_name:
                calls.append(call)
    return calls


def _assert_response_contains(trace: AgentTrace, a: Assertion) -> RuleResult:
    text = a.text or a.value
    matched = [r for r in _responses(trace, a.turn_index) if text in r]
    passed = bool(matched)
    return RuleResult(
        assertion=a.type,
        passed=passed,
        actual=matched[0] if matched else None,
        expected=text,
        evidence=f"turn_index={a.turn_index}" if a.turn_index is not None else "any_turn",
    )


def _assert_response_contains_any(trace: AgentTrace, a: Assertion) -> RuleResult:
    values = a.values or ([a.text] if a.text else [a.value])
    responses = _responses(trace, a.turn_index)
    passed = any(any(v in r for v in values) for r in responses)
    return RuleResult(
        assertion=a.type,
        passed=passed,
        actual=responses[0] if responses else None,
        expected=str(values),
        evidence=f"turn_index={a.turn_index}" if a.turn_index is not None else "any_turn",
    )


def _assert_response_not_contains(trace: AgentTrace, a: Assertion) -> RuleResult:
    values = a.values or ([a.text] if a.text else [a.value])
    responses = _responses(trace)
    violated = [r for r in responses if any(v in r for v in values)]
    passed = not violated
    return RuleResult(
        assertion=a.type,
        passed=passed,
        actual=violated[0] if violated else None,
        expected=f"not contain {values}",
        evidence="all_turns",
    )


def _assert_memory_contains(trace: AgentTrace, a: Assertion) -> RuleResult:
    actual = trace.final_memory.get(a.key)
    passed = a.key in trace.final_memory and actual == a.value
    return RuleResult(
        assertion=a.type,
        passed=passed,
        actual=str(actual),
        expected=f"{a.key}={a.value}",
        evidence="final_memory",
    )


def _assert_memory_not_contains(trace: AgentTrace, a: Assertion) -> RuleResult:
    present = a.key in trace.final_memory
    passed = not present
    return RuleResult(
        assertion=a.type,
        passed=passed,
        actual=str(trace.final_memory.get(a.key)),
        expected=f"{a.key} absent",
        evidence="final_memory",
    )


def _assert_emotion_state_equals(trace: AgentTrace, a: Assertion) -> RuleResult:
    passed = trace.final_emotion == a.value
    return RuleResult(
        assertion=a.type,
        passed=passed,
        actual=trace.final_emotion,
        expected=str(a.value),
        evidence="final_emotion",
    )


def _assert_emotion_state_in(trace: AgentTrace, a: Assertion) -> RuleResult:
    values = a.values or []
    passed = trace.final_emotion in values
    return RuleResult(
        assertion=a.type,
        passed=passed,
        actual=trace.final_emotion,
        expected=str(values),
        evidence="final_emotion",
    )


def _assert_emotion_transition(trace: AgentTrace, a: Assertion) -> RuleResult:
    turns = trace.turns
    initial = turns[0].state_after.mood if turns else trace.final_emotion
    final = trace.final_emotion
    if a.direction:
        iv = EMOTION_VALENCE.get(initial or "", 0)
        fv = EMOTION_VALENCE.get(final or "", 0)
        if a.direction == "more_positive":
            passed = fv > iv
        elif a.direction == "more_negative":
            passed = fv < iv
        else:
            passed = fv == iv
        expected = f"direction={a.direction}"
    else:
        passed = (initial == a.from_value) and (final in (a.to_values or []))
        expected = f"{a.from_value} -> {a.to_values}"
    return RuleResult(
        assertion=a.type,
        passed=passed,
        actual=f"{initial} -> {final}",
        expected=expected,
        evidence="emotion_transition",
    )


def _assert_tool_called(trace: AgentTrace, a: Assertion) -> RuleResult:
    calls = _tool_calls(trace, a.tool_name)
    return RuleResult(
        assertion=a.type,
        passed=bool(calls),
        actual=str(len(calls)) if calls else "0",
        expected=a.tool_name,
        evidence="tool_calls",
    )


def _assert_tool_not_called(trace: AgentTrace, a: Assertion) -> RuleResult:
    calls = _tool_calls(trace, a.tool_name)
    return RuleResult(
        assertion=a.type,
        passed=not calls,
        actual=str(len(calls)),
        expected=f"{a.tool_name} absent",
        evidence="tool_calls",
    )


def _assert_tool_args_match(trace: AgentTrace, a: Assertion) -> RuleResult:
    calls = _tool_calls(trace, a.tool_name)
    expected = a.args or {}
    matched = [c for c in calls if all(c.arguments.get(k) == v for k, v in expected.items())]
    passed = bool(calls) and bool(matched)
    return RuleResult(
        assertion=a.type,
        passed=passed,
        actual=str([c.arguments for c in calls]),
        expected=str(expected),
        evidence="tool_args",
    )


def _assert_tool_status_equals(trace: AgentTrace, a: Assertion) -> RuleResult:
    calls = _tool_calls(trace, a.tool_name)
    matched = [c for c in calls if c.status == a.status]
    passed = bool(matched)
    return RuleResult(
        assertion=a.type,
        passed=passed,
        actual=str([c.status for c in calls]),
        expected=str(a.status),
        evidence="tool_status",
    )


def _assert_response_matches_tool_result(trace: AgentTrace, a: Assertion) -> RuleResult:
    calls = _tool_calls(trace, a.tool_name)
    results = [c.result for c in calls if c.status == "completed" and isinstance(c.result, str)]
    responses = _responses(trace)
    passed = bool(results) and any(any(res in r for res in results) for r in responses)
    return RuleResult(
        assertion=a.type,
        passed=passed,
        actual=responses[0] if responses else None,
        expected=str(results),
        evidence="tool_result",
    )


def _assert_latency_below(trace: AgentTrace, a: Assertion) -> RuleResult:
    max_ms = a.max_ms if a.max_ms is not None else a.value
    latencies = [t.latency_ms for t in trace.turns]
    passed = all(lat < max_ms for lat in latencies) if latencies else True
    return RuleResult(
        assertion=a.type,
        passed=passed,
        actual=str(max(latencies) if latencies else 0),
        expected=f"<{max_ms}",
        evidence="latency",
    )


_ASSERTION_EVALUATORS: dict[str, Callable[[AgentTrace, Assertion], RuleResult]] = {
    "response_contains": _assert_response_contains,
    "response_contains_any": _assert_response_contains_any,
    "response_not_contains": _assert_response_not_contains,
    "memory_contains": _assert_memory_contains,
    "memory_not_contains": _assert_memory_not_contains,
    "emotion_state_equals": _assert_emotion_state_equals,
    "emotion_state_in": _assert_emotion_state_in,
    "emotion_transition": _assert_emotion_transition,
    "tool_called": _assert_tool_called,
    "tool_not_called": _assert_tool_not_called,
    "tool_args_match": _assert_tool_args_match,
    "tool_status_equals": _assert_tool_status_equals,
    "response_matches_tool_result": _assert_response_matches_tool_result,
    "latency_below": _assert_latency_below,
}


class RuleEvaluator:
    """Evaluates a case's assertions against a version's trace."""

    def evaluate(self, trace: AgentTrace, assertions: list[Assertion]) -> list[RuleResult]:
        results: list[RuleResult] = []
        for assertion in assertions:
            evaluator = _ASSERTION_EVALUATORS.get(assertion.type)
            if evaluator is None:
                raise AssertionTypeError(
                    f"unknown assertion type {assertion.type!r}",
                    context={"assertion_type": assertion.type},
                )
            results.append(evaluator(trace, assertion))
        return results

    def all_passed(self, results: list[RuleResult]) -> bool:
        return bool(results) and all(r.passed for r in results)
