"""LangGraph state graph for the AgentGuard agent loop.

Builds the ``orient -> review -> {tools | verify | finalize} -> orient`` cycle
with conditional routing driven by the ``decision`` produced by the review node.
Each non-finalize branch returns to ``orient`` so the OODA cycle completes on
every iteration. The loop is bounded in server code by the step/tool-call budget
and loop detection enforced in the review node; the recursion limit is passed at
invoke time via ``config``.

``messages`` uses ``operator.add`` so nodes return only their *incremental*
message list and the graph concatenates them, keeping the trajectory auditable
without relying on LangGraph's tool-call pairing semantics. All other fields are
plain (overwritten) fields, so nodes return the full updated list.
"""

from typing import Any, Dict

from langgraph.graph import END, START, StateGraph

from agentguard.analysis.tools.base import ToolRegistry
from agentguard.core.policy import AgentPolicy
from agentguard.core.schemas import AgentState
from agentguard.orchestration.nodes import finalize_node, orient_node, review_node, tools_node, verify_node
from agentguard.orchestration.state import AgentGraphState


def _route(state: AgentGraphState) -> str:
    decision = state.get("decision")
    if decision is None:
        return "finalize"
    if decision.action == "tools":
        return "tools"
    if decision.action == "verify":
        return "verify"
    return "finalize"


def build_graph(llm: Any, registry: ToolRegistry, policy: AgentPolicy, verify_llm: Any = None):
    """Assemble the compiled state graph.

    ``llm`` is an ``AgentLLM`` (or a mock exposing ``complete``); ``registry`` is
    the tool whitelist; ``policy`` supplies the server-enforced budgets.
    ``verify_llm`` optionally selects a different model for the independent
    verification pass, defaulting to ``llm``.
    """
    verifier = verify_llm or llm

    async def _orient(state: AgentGraphState) -> Dict[str, Any]:
        return await orient_node(AgentState(**state), policy)

    async def _review(state: AgentGraphState) -> Dict[str, Any]:
        return await review_node(AgentState(**state), llm, registry, policy)

    async def _tools(state: AgentGraphState) -> Dict[str, Any]:
        return await tools_node(AgentState(**state), registry, policy)

    async def _verify(state: AgentGraphState) -> Dict[str, Any]:
        return await verify_node(AgentState(**state), verifier, registry, policy)

    async def _finalize(state: AgentGraphState) -> Dict[str, Any]:
        return await finalize_node(AgentState(**state))

    graph = StateGraph(AgentGraphState)

    graph.add_node("orient", _orient)
    graph.add_node("review", _review)
    graph.add_node("tools", _tools)
    graph.add_node("verify", _verify)
    graph.add_node("finalize", _finalize)

    graph.add_edge(START, "orient")
    graph.add_edge("orient", "review")
    graph.add_conditional_edges("review", _route, {"tools": "tools", "verify": "verify", "finalize": "finalize"})
    graph.add_edge("tools", "orient")
    graph.add_edge("verify", "orient")
    graph.add_edge("finalize", END)

    return graph.compile()
