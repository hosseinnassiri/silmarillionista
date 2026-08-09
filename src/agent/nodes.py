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

Examples:
Q: "What is Turin's assumed name in Nargothrond?" -> relational (alias_resolution)
Q: "Who is Galadriel?" -> semantic (character_explainer)
Q: "Who were the sons of Finarfin?" -> relational (family_tree)
Q: "Compare Thingol and Finwe as kings." -> both (character_comparison)
Q: "What happened during the Dagor Bragollach?" -> semantic (event_explainer)
Q: "Did the founding of Gondolin happen before or after the Dagor Aglareb?" -> relational (timeline)
Q: "What happened between the founding of Doriath and the coming of the Noldor?" -> both (events_between)
Q: "Describe the city of Nargothrond." -> semantic (location_description)
Q: "How did the Noldor cross into Middle-earth from Aman?" -> relational (journey_path)
Q: "What did Feanor say when he swore his oath?" -> semantic (quotes)
Q: "What is connected to the theme of the Silmarils' curse?" -> both (related_topics)
Q: "How is Galadriel related to Finwe?" -> relational (relationships)
Q: "Who are the enemies of Doriath?" -> relational (allies_enemies)
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

    update: dict = {"graph_context": result}
    if not result.get("records") and state.get("route") == "relational":
        # The graph had nothing (e.g. entity-id mismatch, or the relation just
        # isn't in the schema) — fall back to vector search rather than leaving
        # the synthesize node with empty context, which invited hallucination.
        # Only safe when graph_retrieve is running alone: on route "both",
        # vector_retrieve runs in the same step and would conflict writing the
        # same state key.
        update["vector_context"] = vector_search(state["question"], k=5)
    return update


SYNTHESIZE_SYSTEM = """\
You are answering questions about J.R.R. Tolkien's The Silmarillion using ONLY \
the context provided below. This is a strict textual-grounding exercise, not a \
test of your general Tolkien knowledge — even if you're confident you know the \
real answer from training data, you MUST NOT use it unless it is actually \
present in the context below. This applies especially to direct quotations: \
never reconstruct or paraphrase a quote as if verbatim — only present text \
as a quote if it appears word-for-word in the context.

Cite chapter/part names when drawing on narrative context. If the context \
doesn't actually answer the question — it's empty, irrelevant, or the question \
is about events/characters outside The Silmarillion's text (e.g. Aragorn's \
later life) — say plainly that it isn't covered in this text rather than \
guessing or filling the gap from outside knowledge. Be concise.
"""

NOT_COVERED_ANSWER = (
    "This isn't covered in the retrieved text — no relevant passages or graph "
    "relationships were found for this question."
)


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

    if not context_parts:
        # Nothing was retrieved from either source (including the graph's own
        # vector fallback) — don't even ask the LLM, since that's exactly the
        # situation where a capable model is tempted to answer from outside
        # knowledge instead of admitting it has nothing.
        return {"answer": NOT_COVERED_ANSWER, "sources": []}

    context = "\n\n".join(context_parts)

    llm = ChatAnthropic(model=CHAT_MODEL)
    response = llm.invoke(
        [
            SystemMessage(content=SYNTHESIZE_SYSTEM),
            HumanMessage(content=f"Context:\n{context}\n\nQuestion: {state['question']}"),
        ]
    )

    return {"answer": response.content, "sources": sorted(set(sources))}
