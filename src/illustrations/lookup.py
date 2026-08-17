"""Match entity mentions in an answer against the pregenerated illustrations
manifest (built by generate.py) and return matching thumbnail URLs.
"""

import json
import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from src.config import ILLUSTRATIONS_MANIFEST
from src.graph.dedupe import normalize

logger = logging.getLogger(__name__)

_manifest: list[dict] | None = None


def _load_manifest() -> list[dict]:
    global _manifest
    if _manifest is None:
        entries: list[dict] = []
        try:
            if ILLUSTRATIONS_MANIFEST.exists():
                entries = json.loads(ILLUSTRATIONS_MANIFEST.read_text(encoding="utf-8"))
        except Exception:
            logger.exception("Failed to load illustrations manifest at %s", ILLUSTRATIONS_MANIFEST)
            entries = []

        for entry in entries:
            names = {entry["id"], *entry.get("aliases", [])}
            entry["_normalized_names"] = sorted({normalize(n) for n in names}, key=len, reverse=True)
        _manifest = entries
    return _manifest


def find_illustrations(text: str, limit: int = 2) -> list[dict]:
    """Scan `text` for mentions of manifest entities. Returns up to `limit`
    matches as [{name, type, url}], in manifest order.
    """
    normalized_text = normalize(text)
    matches: list[dict] = []
    seen_ids: set[str] = set()

    for entry in _load_manifest():
        if entry["id"] in seen_ids:
            continue
        for name in entry["_normalized_names"]:
            if re.search(rf"\b{re.escape(name)}\b", normalized_text):
                matches.append({"name": entry["id"], "type": entry["type"], "url": f"/illustrations/{entry['file']}"})
                seen_ids.add(entry["id"])
                break
        if len(matches) >= limit:
            break

    return matches


def get_illustration(entity_id: str) -> dict | None:
    """Exact (normalized) id-or-alias lookup — for callers that already know
    the canonical entity id, rather than scanning free text for mentions.
    Checks aliases too, not just the primary id: a caller may be passing an
    id from a different graph than the one the manifest's aliases were
    curated against (e.g. prod's independently-extracted "Battle At Sarn
    Athrad" vs. the manifest's own "Battle Of Sarn Athrad"), which is
    exactly what those aliases exist to bridge.
    """
    target = normalize(entity_id)
    for entry in _load_manifest():
        if target in entry["_normalized_names"]:
            return {"name": entry["id"], "type": entry["type"], "url": f"/illustrations/{entry['file']}"}
    return None
