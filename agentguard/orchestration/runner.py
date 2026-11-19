"""Independent entry point for the AgentGuard agent loop.

The runner builds the tool registry from already-loaded PR diff files, assembles
the LangGraph, and invokes it. It stays separate from ``PRReviewer`` so the
existing ``/review`` command is untouched; enabling the agent is gated by the
``[agent_exec]`` ``enabled`` setting and by the caller choosing to use this
runner.

Two configured models are used per run: the first (review) pass and the
independent (verify) pass. Empty settings fall back to ``config.model`` so a
model swap never requires a code change. The workspace read-only MCP tool is
registered only when explicitly enabled with a root directory.
"""

from typing import Any, List, Optional

from agentguard.analysis.tools import (
    FindReferencesTool,
    ReadFileContextTool,
    RunStaticAnalysisTool,
    build_workspace_tool,
    default_registry,
)
from agentguard.core.llm import AgentLLM
from agentguard.core.policy import load_policy
from agentguard.core.schemas import AgentState
from agentguard.orchestration.graph import build_graph
from pr_agent.config_loader import get_settings


def is_enabled() -> bool:
    """Return True when the AgentGuard agent is explicitly enabled."""
    agent_exec = get_settings().get("agent_exec", {})
    return bool(agent_exec.get("enabled", False))


class ReviewAgentRunner:
    """Runs the bounded tool-use review loop over a PR diff."""

    def __init__(self, ai_handler_factory=None, llm: Optional[AgentLLM] = None) -> None:
        self._policy = load_policy()
        # An injected llm wins (used by the federation to share a global budget);
        # otherwise AgentLLM defaults to LiteLLMAIHandler and None must not override it.
        if llm is not None:
            self._llm = llm
        elif ai_handler_factory is None:
            self._llm = AgentLLM(model=self._policy.review_model or None)
        else:
            self._llm = AgentLLM(ai_handler_factory, model=self._policy.review_model or None)
        # The verifier may use a stronger configured model, sharing the same
        # handler/client. When no distinct model is configured this is the
        # same object, so the default path is unchanged.
        verify_model = self._policy.verify_model or self._policy.review_model or None
        with_model = getattr(self._llm, "with_model", None)
        self._verify_llm = with_model(verify_model) if callable(with_model) else self._llm

    def build_registry(self, diff_files: List[Any]):
        """Build the whitelist: built-in read-only tools plus optional workspace tool."""
        tools = [
            ReadFileContextTool(diff_files),
            FindReferencesTool(diff_files),
            RunStaticAnalysisTool(diff_files),
        ]
        workspace_tool = build_workspace_tool()
        if workspace_tool is not None:
            tools.append(workspace_tool)
        return default_registry(*tools)

    async def run(self, diff_files: List[Any], findings: Optional[List[Any]] = None) -> AgentState:
        """Execute the loop and return the final state (findings + final_answer)."""
        registry = self.build_registry(diff_files)
        graph = build_graph(self._llm, registry, self._policy, verify_llm=self._verify_llm)

        initial: dict[str, Any] = {
            "messages": [],
            "findings": list(findings or []),
            "tool_results": [],
            "decision": None,
            "step": 0,
            "final_answer": None,
            "orientation": None,
            "decision_history": [],
            "audit_events": [],
            "trajectory": [],
        }

        result = await graph.ainvoke(
            initial,
            # Each agent step maps to several graph super-steps (orient + review
            # + tools/verify), so allow ~3x the step budget plus a small margin.
            config={"recursion_limit": self._policy.max_steps * 3 + 4},
        )
        return AgentState(**result)
