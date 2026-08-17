"""One-off batch script: generate pregenerated illustrations for a curated
shortlist of Silmarillion characters/places/events/creatures.

Talks to TWO different Azure OpenAI resources:
- The project's normal chat deployment (src.llm.get_chat_llm()) to write a
  visual-description prompt grounded in retrieved book text.
- A SEPARATE, TEMPORARY Azure OpenAI resource with a gpt-image-1 deployment
  (gpt-image-1 isn't available in canadacentral, where the main deployed
  resource lives — see README's "Illustrations" section for the az commands
  to create/tear down that temporary resource). Point this script at it via
  AZURE_OPENAI_IMAGE_ENDPOINT / AZURE_OPENAI_IMAGE_API_KEY env vars; these
  aren't in src/config.py since they're only ever used here, never by the
  deployed app.

Idempotent: entities already in manifest.json with their image file still on
disk are skipped, so reruns only do new/missing work. Pass an integer to
generate only that many *new* images this run (e.g. `... generate.py 3` for a
small test batch before running the full shortlist).
"""

import base64
import json
import os
import sys
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_neo4j import Neo4jGraph
from openai import AzureOpenAI, BadRequestError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from src.config import ILLUSTRATIONS_DIR, ILLUSTRATIONS_MANIFEST, NEO4J_PASSWORD, NEO4J_URI, NEO4J_USERNAME
from src.graph.dedupe import normalize
from src.llm import get_chat_llm
from src.vectorstore.retriever import vector_search

# gpt-image-1 requires api_version >= 2025-04-01-preview — separate from the
# main app's AZURE_OPENAI_API_VERSION, which targets a different resource.
IMAGE_API_VERSION = "2025-04-01-preview"
IMAGE_DEPLOYMENT = os.environ.get("AZURE_OPENAI_IMAGE_DEPLOYMENT", "gpt-image-1")

# Curated shortlist grounded in the live graph's node connectivity (see the
# illustrations plan). Names are resolved against the graph's actual node
# ids via normalize() below, so exact diacritics/spelling here don't matter —
# entities with no matching graph node still get illustrated, just without
# graph-derived aliases/type (see _entity_info's fallback).
SHORTLIST = [
    # Characters/beings
    "Morgoth", "Sauron", "Feanor", "Fingolfin", "Luthien", "Beren", "Turin",
    "Hurin", "Thingol", "Turgon", "Earendil", "Ungoliant",
    # Valar/Maiar
    "Manwe", "Varda", "Melian",
    # Places
    "Valinor", "Gondolin", "Doriath", "Angband", "Nargothrond", "Numenor",
    # Events
    "Dagor Bragollach", "Nirnaeth Arnoediad", "Kinslaying At Alqualonde",
    "War Of Wrath", "Oath Of Feanor",
    # Objects/creatures
    "Silmaril", "Two Trees", "Glaurung", "Carcharoth", "Huan",
    # Battles (broadened coverage — grounded against the live graph's
    # actual :Event nodes, see the timeline/major_events plan)
    "Battle Of The Powers", "Dagor-Nuin-Giliath", "Dagor Aglareb",
    "Battle Of Sarn Athrad", "Fall Of Gondolin", "Assault On The Havens Of Sirion",
    "Sons Of Feanor'S Assault On Doriath", "Battle Of Tumhalad",
    # Remaining curated timeline events (full illustration coverage for the
    # chevron-strip /timeline redesign — see MAJOR_EVENTS in major_events.py)
    "Music Of The Ainur", "Chaining Of Melkor", "Spring Of Arda",
    "Darkening Of Valinor", "Doom Of The Noldor", "Burning Of The Ships At Losgar",
    "Crossing Of The Helcaraxe", "Mereth Aderthad", "Siege Of Angband",
    "Downfall Of Numenor", "Siege Of Barad-Dur", "Battle Of Dagorlad",
    "White Council", "Assault Upon Dol Guldur", "War Of The Ring",
    "Destruction Of The Ring",
]

STYLE_GUIDE = """\
Illustration style: a single richly painted fantasy illustration — watercolor/
gouache or digital matte-painting texture, never flat, vector, or cartoon.
Cinematic, dramatic lighting: strong directional light and deep shadow, often
with one glowing focal point (a jewel, an eye, a blade, the sun or moon).
Epic sense of scale, with figures or structures often dwarfed by landscape,
architecture, or monsters. No text, no logos, no watermarks, no panel borders.

Choose the palette to match the mood of what is depicted:
- Luminous mode — scenes of glory, divinity, or peace (Valinor, the Two
  Trees, the Valar, unfallen cities): warm gold, white, soft blue; radiant
  backlighting; serene or awe-inspiring, not violent.
- Shadow mode — scenes of darkness, corruption, ruin, or tragedy (Morgoth,
  Angband, battles, deaths, monsters): near-monochrome dark palette with
  embers of red/orange or a single cold light source; oppressive, high-contrast.
"""

PROMPT_WRITER_SYSTEM = f"""\
You write image-generation prompts for illustrations of J.R.R. Tolkien's The
Silmarillion.

{STYLE_GUIDE}

Given an entity name, its type, and passages retrieved from the book, write a
single vivid visual description (100-150 words) suitable as an image prompt.
Ground every visual detail in what the passages actually describe — do not
invent details, characters, or events not present in them, and do not draw on
outside knowledge of Tolkien's work beyond this text. Do not include any
text, caption, or the entity's name as writing within the image itself.
Output only the prompt itself, no preamble.
"""


def _slug(entity_id: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in entity_id.lower()).strip("-")


def _load_manifest() -> list[dict]:
    if ILLUSTRATIONS_MANIFEST.exists():
        return json.loads(ILLUSTRATIONS_MANIFEST.read_text(encoding="utf-8"))
    return []


def _save_manifest(entries: list[dict]) -> None:
    ILLUSTRATIONS_MANIFEST.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")


def _build_id_index(graph: Neo4jGraph) -> dict[str, str]:
    rows = graph.query("MATCH (n:__Entity__) RETURN n.id AS id")
    return {normalize(r["id"]): r["id"] for r in rows if r["id"]}


def _entity_info(graph: Neo4jGraph, id_index: dict[str, str], shortlist_name: str) -> dict:
    canonical_id = id_index.get(normalize(shortlist_name))
    if canonical_id is None:
        # No matching graph node (e.g. a concept like "Two Trees" that the
        # extractor never captured as a discrete entity) — still illustrate
        # it, just without graph-derived aliases/type; vector_search below
        # doesn't require a graph node to find grounding passages.
        return {"canonical_id": shortlist_name, "type": "Concept", "aliases": []}

    rows = graph.query(
        "MATCH (n {id: $id}) "
        "OPTIONAL MATCH (n)-[:ALSO_KNOWN_AS]-(alias) "
        "RETURN labels(n) AS labels, collect(DISTINCT alias.id) AS aliases",
        params={"id": canonical_id},
    )
    labels = [l for l in rows[0]["labels"] if l != "__Entity__"] if rows else []
    raw_aliases = [a for a in rows[0]["aliases"] if a] if rows else []

    # ALSO_KNOWN_AS is noisy — the extractor sometimes links closely-related
    # but distinct entities (parent/child, person/place) rather than true
    # epithets. The one class of noise this can catch mechanically: never let
    # another shortlisted entity's own name become an alias here — that's an
    # unambiguous collision (e.g. "Silmaril" showing up as an alias of Beren,
    # when Silmaril is itself a separate shortlisted entity), and lookup.py
    # would otherwise show the wrong thumbnail whenever the other entity's
    # name appears. Other noise (e.g. a genuinely wrong ALSO_KNOWN_AS
    # relationship to an unrelated person) isn't mechanically detectable
    # here and needs a manual look at manifest.json after regenerating.
    other_shortlisted = {normalize(n) for n in SHORTLIST if n != shortlist_name}
    aliases = [a for a in raw_aliases if normalize(a) not in other_shortlisted]

    return {"canonical_id": canonical_id, "type": labels[0] if labels else "Entity", "aliases": aliases}


def _write_image_prompt(chat_llm, entity_id: str, entity_type: str) -> str:
    docs = vector_search(entity_id, k=4)
    passages = "\n\n".join(d.page_content for d in docs)
    response = chat_llm.invoke(
        [
            SystemMessage(content=PROMPT_WRITER_SYSTEM),
            HumanMessage(content=f"Entity: {entity_id} ({entity_type})\n\nPassages:\n{passages}"),
        ]
    )
    return response.text.strip()


def _generate_image(image_client: AzureOpenAI, prompt: str) -> bytes:
    result = image_client.images.generate(
        model=IMAGE_DEPLOYMENT,
        prompt=prompt,
        size="1024x1024",
        quality="high",
        n=1,
        output_format="png",
        moderation="low",
    )
    return base64.b64decode(result.data[0].b64_json)


def main() -> None:
    max_new = int(sys.argv[1]) if len(sys.argv) > 1 else None

    image_endpoint = os.environ["AZURE_OPENAI_IMAGE_ENDPOINT"]
    image_api_key = os.environ["AZURE_OPENAI_IMAGE_API_KEY"]

    ILLUSTRATIONS_DIR.mkdir(parents=True, exist_ok=True)
    manifest_by_id = {e["id"]: e for e in _load_manifest()}

    graph = Neo4jGraph(url=NEO4J_URI, username=NEO4J_USERNAME, password=NEO4J_PASSWORD)
    id_index = _build_id_index(graph)
    chat_llm = get_chat_llm()
    image_client = AzureOpenAI(azure_endpoint=image_endpoint, api_key=image_api_key, api_version=IMAGE_API_VERSION)

    generated = 0
    for shortlist_name in SHORTLIST:
        info = _entity_info(graph, id_index, shortlist_name)
        entity_id = info["canonical_id"]

        existing = manifest_by_id.get(entity_id)
        if existing and (ILLUSTRATIONS_DIR / existing["file"]).exists():
            continue

        if max_new is not None and generated >= max_new:
            print(f"Reached limit of {max_new} new images, stopping.")
            break

        print(f"--- {entity_id} ({info['type']}) ---")
        prompt = _write_image_prompt(chat_llm, entity_id, info["type"])
        print(f"  prompt: {prompt[:100]}...")

        try:
            image_bytes = _generate_image(image_client, prompt)
        except BadRequestError as e:
            print(f"  SKIPPED (content filter or bad request): {e}")
            continue

        filename = f"{_slug(entity_id)}.png"
        (ILLUSTRATIONS_DIR / filename).write_bytes(image_bytes)
        manifest_by_id[entity_id] = {
            "id": entity_id,
            "aliases": info["aliases"],
            "type": info["type"],
            "file": filename,
            "prompt": prompt,
        }
        _save_manifest(list(manifest_by_id.values()))
        generated += 1
        print(f"  saved {filename}")

    print(f"Done. {generated} generated this run, {len(manifest_by_id)} total in manifest.")


if __name__ == "__main__":
    main()
