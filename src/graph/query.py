"""Cypher generation/execution wrapper around the Neo4j knowledge graph."""

import sys
from pathlib import Path

from langchain_anthropic import ChatAnthropic
from langchain_community.chains.graph_qa.cypher import GraphCypherQAChain
from langchain_community.chains.graph_qa.prompts import CYPHER_GENERATION_PROMPT
from langchain_community.graphs import Neo4jGraph
from langchain_core.prompts import PromptTemplate

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from src.config import CHAT_MODEL, NEO4J_PASSWORD, NEO4J_URI, NEO4J_USERNAME

_chain: GraphCypherQAChain | None = None

CYPHER_PROMPT = PromptTemplate(
    input_variables=CYPHER_GENERATION_PROMPT.input_variables,
    template=CYPHER_GENERATION_PROMPT.template.replace(
        "Instructions:\n",
        "Instructions:\n"
        "Entity names in this graph were extracted by an LLM and have inconsistent "
        "spelling/accents/capitalization for the same character or place (e.g. "
        "'Feanor', 'Fëanor', 'FEANOR' may all refer to the same node, only one of "
        "which actually exists). Never match node names with exact equality "
        "(n.id = \"...\"). Always match using "
        "apoc.text.clean(n.id) = apoc.text.clean(\"Name From Question\"), which "
        "lowercases and strips accents/punctuation from both sides.\n"
        "Never traverse or return MENTIONS relationships or :Document nodes — "
        "those are internal provenance links from source text chunks to entities, "
        "not part of the domain schema, and their text content is irrelevant to "
        "the question. Only use the domain relationship types listed in the schema "
        "below (PARENT_OF, SPOUSE_OF, RULED, ALLIED_WITH, ENEMY_OF, etc.).\n",
    ),
)


def _get_chain() -> GraphCypherQAChain:
    global _chain
    if _chain is None:
        graph = Neo4jGraph(url=NEO4J_URI, username=NEO4J_USERNAME, password=NEO4J_PASSWORD)
        llm = ChatAnthropic(model=CHAT_MODEL)
        _chain = GraphCypherQAChain.from_llm(
            llm=llm,
            graph=graph,
            cypher_prompt=CYPHER_PROMPT,
            exclude_types=["MENTIONS", "Document"],
            verbose=True,
            validate_cypher=True,
            return_intermediate_steps=True,
            allow_dangerous_requests=True,
            top_k=25,
        )
    return _chain


def graph_query(question: str) -> dict:
    """Returns {"answer": str, "cypher": str, "records": list}."""
    result = _get_chain().invoke({"query": question})
    steps = result.get("intermediate_steps", [])
    cypher = steps[0].get("query", "") if steps else ""
    records = steps[1].get("context", []) if len(steps) > 1 else []
    return {"answer": result["result"], "cypher": cypher, "records": records}


if __name__ == "__main__":
    question = sys.argv[1] if len(sys.argv) > 1 else "Who are the children of Feanor?"
    result = graph_query(question)
    print(f"\nCypher: {result['cypher']}")
    print(f"Records: {result['records']}")
    print(f"\nAnswer: {result['answer']}")
