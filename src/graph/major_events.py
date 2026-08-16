"""Curated, hand-ordered list of "major" events for the /timeline view.

Distinct from timeline.py: that script decides which *era* an event
happened in (HAPPENED_DURING -> :Era, era.sequence). This module decides,
within an era, which events are worth showing at all (73 linked :Event
nodes include a lot of LLM-spelling duplicates -- e.g. "Dagor Bragollach"
and "Bragollach" are the same event) and what order to show them in.

Ordering is intentionally NOT derived from scanning chunks.json for each
event's first text mention -- that was tried and rejected. "Battle Of Sarn
Athrad"'s first textual match is a passing mention of the ford in chapter
10 ("Of the Sindar"); the actual battle is narrated in chapter 22. A
generic-name text scan silently mis-orders events toward whichever chapter
first name-drops a place, not the chapter the event actually happens in --
worse than a gap, since a wrong order looks correct until checked.

Instead, MAJOR_EVENTS below is a single hand-curated list, in the actual
book chapter order each event belongs to (verified against chunks.json's
own chapter_title metadata -- some are unambiguous from the title alone,
e.g. ch.20 "Of the Fifth Battle: Nirnaeth Arnoediad", ch.23 "Of Tuor and
the Fall of Gondolin", ch.22 "Of the Ruin of Doriath"). List position is
the order -- no runtime scan needed.
"""

import sys
from pathlib import Path

from langchain_neo4j import Neo4jGraph

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from src.config import NEO4J_PASSWORD, NEO4J_URI, NEO4J_USERNAME

MAJOR_EVENTS = [
    # Years of the Lamps (ch. 1-3)
    "Music Of The Ainur",
    "Battle Of The Powers",
    "Chaining Of Melkor",
    "Spring Of Arda",
    # Years of the Trees (ch. 8-9)
    "Darkening Of Valinor",
    "Oath Of Fëanor",
    "Kinslaying At Alqualondé",
    "Doom Of The Noldor",
    "Burning Of The Ships At Losgar",
    # Years of the Sun / First Age (ch. 13, 18, 20-24)
    "Crossing Of The Helcaraxé",
    "Dagor-Nuin-Giliath",
    "Mereth Aderthad",
    "Dagor Aglareb",
    "Siege Of Angband",
    "Dagor Bragollach",
    "Nirnaeth Arnoediad",
    "Battle Of Tumhalad",
    "Fall Of Gondolin",
    "Sons Of Féanor'S Assault On Doriath",
    "Battle Of Sarn Athrad",
    "Assault On The Havens Of Sirion",
    "War Of Wrath",
    # Second Age
    "Downfall Of Númenor",
    "Siege Of Barad-Dûr",
    # Third Age
    "Battle Of Dagorlad",
    "White Council",
    "Assault Upon Dol Guldur",
    "War Of The Ring",
    "Destruction Of The Ring",
]

_graph: Neo4jGraph | None = None


def _get_graph() -> Neo4jGraph:
    global _graph
    if _graph is None:
        _graph = Neo4jGraph(url=NEO4J_URI, username=NEO4J_USERNAME, password=NEO4J_PASSWORD)
    return _graph


def get_timeline() -> list[dict]:
    """Returns eras in sequence order, each with its major events in curated order.

    [{"era": str, "sequence": int, "events": [{"id": str, "order": int}, ...]}]
    """
    rows = _get_graph().query(
        "MATCH (e:Event)-[:HAPPENED_DURING]->(era:Era) "
        "WHERE e.timeline_order IS NOT NULL "
        "RETURN e.id AS id, e.timeline_order AS order, era.id AS era, era.sequence AS seq "
        "ORDER BY seq, order"
    )

    eras: dict[str, dict] = {}
    for row in rows:
        era = eras.setdefault(row["era"], {"era": row["era"], "sequence": row["seq"], "events": []})
        era["events"].append({"id": row["id"], "order": row["order"]})

    return sorted(eras.values(), key=lambda e: e["sequence"])


def main() -> None:
    graph = _get_graph()
    existing = graph.query("MATCH (e:Event) RETURN e.id AS id")
    existing_ids = {r["id"] for r in existing}

    set_count = 0
    missing = []
    for order, event_id in enumerate(MAJOR_EVENTS):
        if event_id not in existing_ids:
            missing.append(event_id)
            continue
        graph.query(
            "MATCH (e {id: $id}) SET e.timeline_order = $order",
            params={"id": event_id, "order": order},
        )
        set_count += 1

    print(f"Set timeline_order on {set_count} events.")
    if missing:
        print(f"Skipped {len(missing)} ids not found as existing :Event nodes: {missing}")


if __name__ == "__main__":
    main()
