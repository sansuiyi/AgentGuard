"""Run a single version (base or candidate) of an agent over one test case.

Each case starts from a fresh ``reset`` so base and candidate never share state;
the same user profile and inputs are replayed deterministically.
"""

from __future__ import annotations

from agentguard.core.enums import Version
from agentguard.core.models import AgentTrace, TestCase, TurnTrace
from agentguard.runtime.adapter import AgentAdapter


class VersionRunner:
    """Executes a test case against one agent instance and builds its trace."""

    def __init__(self, agent: AgentAdapter, version: Version, run_id: str, version_label: str = "") -> None:
        self._agent = agent
        self._version = version
        self._run_id = run_id
        self._version_label = version_label or version.value

    @property
    def version(self) -> Version:
        return self._version

    def run_case(self, case: TestCase) -> AgentTrace:
        trace_id = f"trace-{self._run_id}-{case.case_id}-{self._version.value}"
        self._agent.reset(case.user_profile)

        turns: list[TurnTrace] = []
        history: list[dict] = []
        status = "success"
        error: str | None = None

        for index, turn in enumerate(case.turns):
            try:
                result = self._agent.invoke(turn.input, history)
            except Exception as exc:  # adapter crash must not take down the whole run
                status = "error"
                error = f"turn {index} invoke failed: {exc}"
                turns.append(
                    TurnTrace(
                        turn_index=index,
                        user_input=turn.input,
                        agent_response="",
                    )
                )
                break

            turns.append(
                TurnTrace(
                    turn_index=index,
                    user_input=turn.input,
                    agent_response=result.response,
                    memory_reads=result.memory_reads,
                    memory_writes=result.memory_writes,
                    tool_calls=result.tool_calls,
                    state_before=result.state_before,
                    state_after=result.state_after,
                    latency_ms=result.latency_ms,
                )
            )
            history.append({"role": "user", "content": turn.input})
            history.append({"role": "assistant", "content": result.response})

        collected = self._agent.collect_trace() if status == "success" else {}

        return AgentTrace(
            trace_id=trace_id,
            run_id=self._run_id,
            case_id=case.case_id,
            version=self._version,
            turns=turns,
            status=status,
            error=error,
            final_memory=collected.get("memory", {}),
            final_emotion=collected.get("emotion"),
        )

    def teardown(self) -> None:
        self._agent.teardown()
