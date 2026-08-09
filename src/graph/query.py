"""Cypher generation/execution wrapper around the Neo4j knowledge graph."""

import sys
from pathlib import Path

from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import PromptTemplate
from langchain_neo4j import GraphCypherQAChain, Neo4jGraph
from langchain_neo4j.chains.graph_qa.cypher import CYPHER_GENERATION_PROMPT, extract_cypher

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
        "below (PARENT_OF, SPOUSE_OF, RULED, ALLIED_WITH, ENEMY_OF, etc.).\n"
        "For timeline/ordering questions (before/after/during/between), do not "
        "search for an event literally named after the question's wording — "
        "instead find the :Event node(s) that actually correspond to what's "
        "being asked (e.g. \"the Noldor returning to Middle-earth\" maps to "
        "an event like 'Exile Of The Noldor' or 'Crossing Of The Helcaraxe'), "
        "traverse (event)-[:HAPPENED_DURING]->(era:Era) to reach their era, "
        "and compare era.sequence (lower sequence = earlier). Known eras in "
        "chronological order: 'Years of the Lamps'(1) < 'Years of the Trees'"
        "(2) < 'Years of the Sun'(3, roughly the First Age) < 'Second Age'"
        "(4) < 'Third Age'(5). If unsure which specific event node matches, "
        "use a CONTAINS match on plausible keywords rather than giving up.\n",
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


def _contains_document_node(value) -> bool:
    """True if a value contains a :Document-shaped node anywhere within it.

    exclude_types only hides MENTIONS/Document from the schema description
    shown to the Cypher-generation LLM — it does NOT stop Neo4j from actually
    matching them when the generated query uses an untyped wildcard pattern
    like (n)-[r]-(m). This is a deterministic backstop that works regardless
    of what shape the generated Cypher happens to take.
    """
    if isinstance(value, dict):
        if "chunk_index" in value:
            return True
        return any(_contains_document_node(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_document_node(v) for v in value)
    return False


def graph_query(question: str) -> dict:
    """Generate Cypher, run it, and return records — skips GraphCypherQAChain's
    own QA-synthesis call, since our agent's synthesize_node redoes that work
    from the records anyway and never reads the chain's own answer. Roughly
    halves the LLM calls per graph query.

    Returns {"cypher": str, "records": list}.
    """
    chain = _get_chain()

    generated_cypher = chain.cypher_generation_chain.invoke(
        {"question": question, "examples": None, "schema": chain.graph_schema}
    )
    generated_cypher = extract_cypher(generated_cypher)
    if chain.cypher_query_corrector:
        generated_cypher = chain.cypher_query_corrector(generated_cypher)

    records = chain.graph.query(generated_cypher)[: chain.top_k] if generated_cypher else []
    records = [row for row in records if not _contains_document_node(row)]
    return {"cypher": generated_cypher, "records": records}


if __name__ == "__main__":
    question = sys.argv[1] if len(sys.argv) > 1 else "Who are the children of Feanor?"
    result = graph_query(question)
    print(f"\nCypher: {result['cypher']}")
    print(f"Records: {result['records']}")
