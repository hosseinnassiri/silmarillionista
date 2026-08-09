"""LangGraph state schema for the agent."""

from typing import Literal, Optional, TypedDict

from langchain_core.documents import Document


class GraphContext(TypedDict):
    answer: str
    cypher: str
    records: list


class AgentState(TypedDict, total=False):
    question: str
    route: Literal["semantic", "relational", "both"]
    vector_context: list[Document]
    graph_context: Optional[GraphContext]
    answer: str
    sources: list[str]
