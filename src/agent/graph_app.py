"""LangGraph assembly: router -> (vector_retrieve | graph_retrieve | both) -> synthesize."""

import sys
from pathlib import Path

from langgraph.graph import END, START, StateGraph

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from src.agent.nodes import (
    graph_retrieve_node,
    route_decision,
    router_node,
    synthesize_node,
    vector_retrieve_node,
)
from src.agent.state import AgentState

_app = None


def build_graph():
    builder = StateGraph(AgentState)
    builder.add_node("router", router_node)
    builder.add_node("vector_retrieve", vector_retrieve_node)
    builder.add_node("graph_retrieve", graph_retrieve_node)
    builder.add_node("synthesize", synthesize_node)

    builder.add_edge(START, "router")
    builder.add_conditional_edges("router", route_decision, ["vector_retrieve", "graph_retrieve"])
    builder.add_edge("vector_retrieve", "synthesize")
    builder.add_edge("graph_retrieve", "synthesize")
    builder.add_edge("synthesize", END)

    return builder.compile()


def get_app():
    global _app
    if _app is None:
        _app = build_graph()
    return _app


def ask(question: str) -> dict:
    return get_app().invoke({"question": question})
