"""Router, retrieve, and synthesize nodes for the agent graph."""

import sys
from pathlib import Path
from typing import Literal

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from src.agent.state import AgentState
from src.config import CHAT_MODEL
from src.graph.query import graph_query
from src.vectorstore.retriever import vector_search

ROUTER_SYSTEM = """\
Classify a question about J.R.R. Tolkien's The Silmarillion into exactly one route:

- semantic: best answered by retrieving narrative prose passages. Covers \
character_explainer, event_explainer, location_description, quotes, journey_path.
- relational: best answered by traversing structured relationships in a \
knowledge graph (parentage, marriage, rulership, alliances, enmity, aliases). \
Covers alias_resolution, family_tree, relationships, allies_enemies, timeline, \
events_between.
- both: needs narrative detail AND relationship structure. Covers \
character_comparison, related_topics, or anything combining the two.

When in doubt between semantic and relational, prefer "both".
"""


class RouteDecision(BaseModel):
    route: Literal["semantic", "relational", "both"]


_router_llm = None


def _get_router_llm():
    global _router_llm
    if _router_llm is None:
        _router_llm = ChatAnthropic(model=CHAT_MODEL).with_structured_output(RouteDecision)
    return _router_llm


def router_node(state: AgentState) -> dict:
    decision: RouteDecision = _get_router_llm().invoke(
        [SystemMessage(content=ROUTER_SYSTEM), HumanMessage(content=state["question"])]
    )
    return {"route": decision.route}


def route_decision(state: AgentState) -> list[str]:
    if state["route"] == "semantic":
        return ["vector_retrieve"]
    if state["route"] == "relational":
        return ["graph_retrieve"]
    return ["vector_retrieve", "graph_retrieve"]


def vector_retrieve_node(state: AgentState) -> dict:
    docs = vector_search(state["question"], k=5)
    return {"vector_context": docs}


def graph_retrieve_node(state: AgentState) -> dict:
    try:
        result = graph_query(state["question"])
    except Exception as e:
        result = {"answer": "", "cypher": "", "records": [], "error": str(e)}
    return {"graph_context": result}


SYNTHESIZE_SYSTEM = """\
You are answering questions about J.R.R. Tolkien's The Silmarillion using ONLY \
the context provided below — do not use outside knowledge. Cite chapter/part \
names when drawing on narrative context. If the context doesn't actually answer \
the question (e.g. it asks about events/characters outside The Silmarillion's \
text, such as Aragorn's later life, or the retrieved context is empty/irrelevant), \
say plainly that it isn't covered in this text rather than guessing. Be concise.
"""


def synthesize_node(state: AgentState) -> dict:
    context_parts = []
    sources: list[str] = []

    for doc in state.get("vector_context") or []:
        meta = doc.metadata
        label = meta["part"] + (
            f" #{meta['chapter_number']}: {meta['chapter_title']}" if meta.get("chapter_number") else ""
        )
        context_parts.append(f"[Narrative — {label}]\n{doc.page_content}")
        sources.append(label)

    graph_context = state.get("graph_context")
    if graph_context and graph_context.get("records"):
        context_parts.append(
            f"[Knowledge graph result]\nCypher: {graph_context['cypher']}\n"
            f"Records: {graph_context['records']}"
        )
        sources.append("knowledge graph")

    context = "\n\n".join(context_parts) if context_parts else "(no context retrieved)"

    llm = ChatAnthropic(model=CHAT_MODEL)
    response = llm.invoke(
        [
            SystemMessage(content=SYNTHESIZE_SYSTEM),
            HumanMessage(content=f"Context:\n{context}\n\nQuestion: {state['question']}"),
        ]
    )

    return {"answer": response.content, "sources": sorted(set(sources))}
