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

from langchain_community.graphs import Neo4jGraph

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from src.config import NEO4J_PASSWORD, NEO4J_URI, NEO4J_USERNAME


def normalize(name: str) -> str:
    decomposed = unicodedata.normalize("NFKD", name)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(stripped.lower().split())


def main() -> None:
    graph = Neo4jGraph(url=NEO4J_URI, username=NEO4J_USERNAME, password=NEO4J_PASSWORD)

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
        degrees = graph.query(
            "UNWIND $eids AS eid MATCH (n) WHERE elementId(n) = eid "
            "RETURN eid, n.id AS id, COUNT { (n)--() } AS degree ORDER BY degree DESC",
            params={"eids": eids},
        )
        ordered_ids = [d["eid"] for d in degrees]
        canonical = degrees[0]["id"]
        print(f"  {key!r}: {[d['id'] for d in degrees]} -> keeping {canonical!r}")

        graph.query(
            "MATCH (n) WHERE elementId(n) IN $eids "
            "WITH collect(n) AS nodes "
            "CALL apoc.refactor.mergeNodes(nodes, {properties: 'discard', mergeRels: true}) "
            "YIELD node RETURN node",
            params={"eids": ordered_ids},
        )

    print(f"Merged {len(dup_groups)} duplicate groups.")


if __name__ == "__main__":
    main()
