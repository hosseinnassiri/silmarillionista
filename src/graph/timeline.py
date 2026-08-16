"""Hand-curated era timeline, linking existing :Event nodes to their era via
HAPPENED_DURING. HAPPENED_DURING extraction from LLMGraphTransformer was too
sparse to answer timeline/ordering questions (implicit chronology in prose is
hard to extract reliably) -- this fills that gap with real Tolkien chronology
instead of relying on further extraction.

Only links events that already exist as :Event nodes in the graph (matched by
diacritic/case-insensitive name) -- never invents new event nodes. Era nodes
are created if they don't already exist (three of the five already do, as
:Event nodes themselves: Years Of The Trees, Years Of The Sun, Third Age).
"""

import sys
import unicodedata
from pathlib import Path

from langchain_neo4j import Neo4jGraph

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from src.config import NEO4J_PASSWORD, NEO4J_URI, NEO4J_USERNAME

ERAS = [
    ("Years of the Lamps", 1),
    ("Years of the Trees", 2),
    ("Years of the Sun", 3),  # roughly the First Age
    ("Second Age", 4),
    ("Third Age", 5),
]

# event name (as best matched against existing extracted spelling) -> era
EVENT_ERA = {
    # Years of the Lamps
    "Music Of The Ainur": "Years of the Lamps",
    "Ainulindale": "Years of the Lamps",
    "Second Music Of The Ainur": "Years of the Lamps",
    "Battle Of The Powers": "Years of the Lamps",
    "First Battle Of The Valar With Melkor": "Years of the Lamps",
    "War Upon Utumno": "Years of the Lamps",
    "Siege Of Utumno": "Years of the Lamps",
    "Chaining Of Melkor": "Years of the Lamps",
    "Spring Of Arda": "Years of the Lamps",
    "Second Spring Of Arda": "Years of the Lamps",
    "Sleep Of Yavanna": "Years of the Lamps",
    # Years of the Trees
    "Days Of Bliss": "Years of the Trees",
    "Days Of The Bliss Of Valinor": "Years of the Trees",
    "Darkening Of Valinor": "Years of the Trees",
    "Nurtale Valinoreva": "Years of the Trees",
    "Oath Of Feanor": "Years of the Trees",
    "Kinslaying": "Years of the Trees",
    "Kinslaying At Alqualonde": "Years of the Trees",
    "Doom Of The Noldor": "Years of the Trees",
    "Doom Of Mandos": "Years of the Trees",
    "Curse Of Mandos": "Years of the Trees",
    "Burning Of The Ships": "Years of the Trees",
    "Burning Of The Ships At Losgar": "Years of the Trees",
    "Exile Of The Noldor": "Years of the Trees",
    "Prophecy Of The North": "Years of the Trees",
    # Years of the Sun / First Age
    "Crossing Of The Helcaraxe": "Years of the Sun",
    "Dagor-Nuin-Giliath": "Years of the Sun",
    "Dagor Aglareb": "Years of the Sun",
    "Siege Of Angband": "Years of the Sun",
    "Mereth Aderthad": "Years of the Sun",
    "Dagor Bragollach": "Years of the Sun",
    "Bragollach": "Years of the Sun",
    "Fell Winter": "Years of the Sun",
    "Long Peace": "Years of the Sun",
    "Contest Of Sauron And Felagund": "Years of the Sun",
    "Nirnaeth Arnoediad": "Years of the Sun",
    "Battle Of Unnumbered Tears": "Years of the Sun",
    "Fourth Battle": "Years of the Sun",
    "Year Of Lamentation": "Years of the Sun",
    "Union Of Maedhros": "Years of the Sun",
    "Quest Of The Silmaril": "Years of the Sun",
    "Quest": "Years of the Sun",
    "Leap Of Beren": "Years of the Sun",
    "Hunting Of The Wolf": "Years of the Sun",
    "Battle Of Sarn Athrad": "Years of the Sun",
    "Fall Of Gondolin": "Years of the Sun",
    "The Fall Of Gondolin": "Years of the Sun",
    "Sack Of Gondolin": "Years of the Sun",
    "Battle Of Tumhalad": "Years of the Sun",
    "Gates Of Summer": "Years of the Sun",
    "Midsummer": "Years of the Sun",
    "Sons Of Feanor'S Assault On Doriath": "Years of the Sun",
    "Assault On The Havens Of Sirion": "Years of the Sun",
    "Orc-Raid On The Haladin": "Years of the Sun",
    "Wars Of Beleriand": "Years of the Sun",
    "War Of Wrath": "Years of the Sun",
    "War Of The Jewels": "Years of the Sun",
    "Change Of The World": "Years of the Sun",
    "Great Battle": "Years of the Sun",
    "That Last Battle": "Years of the Sun",
    "Last Battle": "Years of the Sun",
    "Third Battle": "Years of the Sun",
    # Second Age
    "Downfall Of Numenor": "Second Age",
    "Drowning Of Numenor": "Second Age",
    "Akallabeth": "Second Age",
    "Black Years": "Second Age",
    "Siege Of Barad-Dur": "Second Age",
    # Third Age
    "White Council": "Third Age",
    "Assault Upon Dol Guldur": "Third Age",
    "Battle Of Dagorlad": "Third Age",
    "War Of The Ring": "Third Age",
    "Destruction Of The Ring": "Third Age",
    "Third Age Of The World": "Third Age",
}


def normalize(name: str) -> str:
    decomposed = unicodedata.normalize("NFKD", name)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(stripped.lower().split())


def main() -> None:
    # refresh_schema=False: this script only runs direct MATCH/MERGE queries,
    # never LangChain's schema-dependent Cypher generation, so it doesn't need
    # apoc.meta.data() — which prod's narrow APOC allowlist doesn't permit
    # (see infra/modules/neo4j.bicep's NEO4J_dbms_security_procedures_allowlist).
    graph = Neo4jGraph(
        url=NEO4J_URI, username=NEO4J_USERNAME, password=NEO4J_PASSWORD, refresh_schema=False
    )

    existing_events = graph.query("MATCH (e:Event) RETURN e.id AS id")
    by_norm = {normalize(r["id"]): r["id"] for r in existing_events}

    era_actual_id = {}
    for era_name, sequence in ERAS:
        norm = normalize(era_name)
        actual_id = by_norm.get(norm, era_name)
        graph.query(
            "MERGE (e {id: $id}) SET e:Era SET e.sequence = $sequence",
            params={"id": actual_id, "sequence": sequence},
        )
        era_actual_id[era_name] = actual_id
    print(f"{len(ERAS)} eras created/updated.")

    linked = 0
    skipped = []
    for event_name, era_name in EVENT_ERA.items():
        norm = normalize(event_name)
        actual_event_id = by_norm.get(norm)
        if actual_event_id is None:
            skipped.append(event_name)
            continue
        graph.query(
            "MATCH (ev {id: $event_id}) MATCH (er {id: $era_id}) "
            "MERGE (ev)-[:HAPPENED_DURING]->(er)",
            params={"event_id": actual_event_id, "era_id": era_actual_id[era_name]},
        )
        linked += 1

    print(f"Linked {linked} events to eras.")
    if skipped:
        print(f"Skipped {len(skipped)} names not found as existing :Event nodes: {skipped}")


if __name__ == "__main__":
    main()
