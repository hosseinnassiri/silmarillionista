"""Run LLMGraphTransformer over all chunks and push the resulting graph to Neo4j.

Input:  data/processed/chunks.json (from ingest/chunk.py)
Output: nodes/relationships written into the configured Neo4j database.

Extraction runs concurrently (CONCURRENCY documents in flight at once) and skips
any chunk that already has a matching :Document node in Neo4j, so the script is
safe to re-run after a partial/interrupted run.
"""

import asyncio
import json
import sys
from pathlib import Path

from langchain_core.documents import Document
from langchain_neo4j import LLMGraphTransformer, Neo4jGraph

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from src.config import CHUNKS_PATH, NEO4J_PASSWORD, NEO4J_URI, NEO4J_USERNAME
from src.graph.dedupe import run_dedupe
from src.graph.schema import ALLOWED_NODES, ALLOWED_RELATIONSHIPS
from src.llm import get_chat_llm

BATCH_SIZE = 20
CONCURRENCY = 8


def load_documents() -> list[Document]:
    if not CHUNKS_PATH.exists():
        raise FileNotFoundError(f"{CHUNKS_PATH} not found — run ingest/chunk.py first.")
    chunks = json.loads(CHUNKS_PATH.read_text(encoding="utf-8"))
    return [Document(page_content=c["text"], metadata=c["metadata"]) for c in chunks]


ADDITIONAL_INSTRUCTIONS = """\
- PARENT_OF must point from the parent to the child (e.g. Hurin -[PARENT_OF]-> Turin, \
because Hurin is Turin's father). Never reverse this direction.
- Only extract a relationship if it is explicitly stated in the text. Do not infer \
parentage, marriage, or rulership from characters merely being mentioned together, \
being kin, or being in the same house/family — e.g. siblings are not PARENT_OF each \
other.
- Use ALSO_KNOWN_AS (as a relationship, not a node property) only for true alternate \
names, epithets, or titles (e.g. Beren -[ALSO_KNOWN_AS]-> Erchamion, Turin \
-[ALSO_KNOWN_AS]-> Turambar). Do not use it for ordinary patronymics like "son of X" \
— those should instead produce a PARENT_OF edge from X to the person.
"""


def build_transformer() -> LLMGraphTransformer:
    llm = get_chat_llm()
    return LLMGraphTransformer(
        llm=llm,
        allowed_nodes=ALLOWED_NODES,
        allowed_relationships=ALLOWED_RELATIONSHIPS,
        additional_instructions=ADDITIONAL_INSTRUCTIONS,
    )


def chunk_key(metadata: dict) -> tuple:
    return (metadata["part"], metadata["chapter_number"], metadata["chunk_index"])


def already_processed_keys(graph: Neo4jGraph) -> set[tuple]:
    rows = graph.query(
        "MATCH (d:Document) RETURN d.part AS part, d.chapter_number AS chapter_number, "
        "d.chunk_index AS chunk_index"
    )
    return {(r["part"], r["chapter_number"], r["chunk_index"]) for r in rows}


async def convert_batch(
    transformer: LLMGraphTransformer, batch: list[Document], semaphore: asyncio.Semaphore
):
    async def process_one(doc: Document):
        async with semaphore:
            return await transformer.aprocess_response(doc)

    return await asyncio.gather(*(process_one(d) for d in batch))


async def main_async() -> None:
    documents = load_documents()
    transformer = build_transformer()
    # refresh_schema=False: this script only runs direct MATCH/CALL queries,
    # never LangChain's schema-dependent Cypher generation, so it doesn't need
    # apoc.meta.data() — which a narrowly-allowlisted Neo4j instance may not permit
    # (see infra/modules/neo4j.bicep's NEO4J_dbms_security_procedures_allowlist).
    graph = Neo4jGraph(
        url=NEO4J_URI, username=NEO4J_USERNAME, password=NEO4J_PASSWORD, refresh_schema=False
    )

    done_keys = already_processed_keys(graph)
    remaining = [d for d in documents if chunk_key(d.metadata) not in done_keys]
    print(f"{len(documents) - len(remaining)} already processed, {len(remaining)} remaining "
          f"(concurrency={CONCURRENCY})")

    semaphore = asyncio.Semaphore(CONCURRENCY)
    total_nodes = 0
    total_rels = 0
    done_so_far = len(documents) - len(remaining)
    for start in range(0, len(remaining), BATCH_SIZE):
        batch = remaining[start : start + BATCH_SIZE]
        graph_documents = await convert_batch(transformer, batch, semaphore)
        graph.add_graph_documents(graph_documents, baseEntityLabel=True, include_source=True)

        batch_nodes = sum(len(gd.nodes) for gd in graph_documents)
        batch_rels = sum(len(gd.relationships) for gd in graph_documents)
        total_nodes += batch_nodes
        total_rels += batch_rels
        done_so_far += len(batch)
        print(
            f"[{done_so_far}/{len(documents)}] "
            f"+{batch_nodes} nodes, +{batch_rels} relationships "
            f"(running total this run: {total_nodes} nodes, {total_rels} relationships)"
        )

    print(f"Done. {total_nodes} nodes, {total_rels} relationships written to Neo4j this run.")

    # Document nodes are kept (already_processed_keys relies on them for
    # resumability), but MENTIONS edges to entities serve no purpose here and
    # pollute any wildcard Cypher traversal like (n)-[r]-(m) with raw chunk
    # text — strip them so the graph stays clean for querying.
    deleted = graph.query("MATCH (:Document)-[r:MENTIONS]-() DELETE r RETURN count(r) AS n")
    print(f"Stripped {deleted[0]['n']} MENTIONS edges (kept Document nodes for resumability).")

    # Entities with inconsistent LLM spelling (e.g. "Feanor"/"Fëanor") show up
    # as separate nodes unless merged — run automatically so this can't be
    # forgotten as a manual follow-up step after extraction.
    run_dedupe(graph)


if __name__ == "__main__":
    asyncio.run(main_async())
