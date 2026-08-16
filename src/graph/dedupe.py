"""Merge duplicate entity nodes caused by inconsistent LLM spelling of the same name
(e.g. "Luthien" / "Lüthien" / "Lúthien" all extracted as distinct entities).

Groups :__Entity__ nodes by a normalized key (diacritics stripped, lowercased,
whitespace collapsed) and merges each group into the highest-degree node using
APOC's mergeNodes, discarding the other nodes' properties (so the canonical
node's own `id` stays a clean single string) and merging parallel relationships.
"""

import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

from langchain_neo4j import Neo4jGraph

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from src.config import NEO4J_PASSWORD, NEO4J_URI, NEO4J_USERNAME


def normalize(name: str) -> str:
    decomposed = unicodedata.normalize("NFKD", name)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(stripped.lower().split())


def _diacritic_score(name: str) -> int:
    """Count of non-ASCII characters, used as a proxy for "closer to the book's
    own Tolkien orthography" (e.g. "Fëanor" over "Feanor") when picking which
    duplicate node's spelling survives the merge.
    """
    return sum(1 for c in name if ord(c) > 127)


def run_dedupe(graph: Neo4jGraph) -> int:
    """Merge duplicate entity nodes in-place. Returns the number of groups merged."""
    rows = graph.query("MATCH (n:__Entity__) RETURN elementId(n) AS eid, n.id AS id")
    groups: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        if r["id"]:
            groups[normalize(r["id"])].append(r["eid"])

    dup_groups = {k: v for k, v in groups.items() if len(v) > 1}
    print(
        f"{len(dup_groups)} duplicate groups found "
        f"({sum(len(v) for v in dup_groups.values())} nodes total, {len(rows)} entities overall)"
    )

    for key, eids in sorted(dup_groups.items()):
        candidates = graph.query(
            "UNWIND $eids AS eid MATCH (n) WHERE elementId(n) = eid "
            "RETURN eid, n.id AS id, COUNT { (n)--() } AS degree",
            params={"eids": eids},
        )
        # Prefer the spelling closest to the book's own orthography (more
        # diacritics), tie-broken by whichever node has the most connections.
        candidates.sort(key=lambda c: (_diacritic_score(c["id"]), c["degree"]), reverse=True)
        ordered_ids = [c["eid"] for c in candidates]
        canonical = candidates[0]["id"]
        print(f"  {key!r}: {[c['id'] for c in candidates]} -> keeping {canonical!r}")

        graph.query(
            "MATCH (n) WHERE elementId(n) IN $eids "
            "WITH collect(n) AS nodes "
            "CALL apoc.refactor.mergeNodes(nodes, {properties: 'discard', mergeRels: true}) "
            "YIELD node RETURN node",
            params={"eids": ordered_ids},
        )

    print(f"Merged {len(dup_groups)} duplicate groups.")
    return len(dup_groups)


def main() -> None:
    # refresh_schema=False: see the same note in extract.py/timeline.py.
    graph = Neo4jGraph(
        url=NEO4J_URI, username=NEO4J_USERNAME, password=NEO4J_PASSWORD, refresh_schema=False
    )
    run_dedupe(graph)


if __name__ == "__main__":
    main()
