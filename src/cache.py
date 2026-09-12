"""Table Storage-backed cache for repeated /ask questions.

Used only by src/api/app.py's POST /ask — never by src/agent/graph_app.py's
ask() itself, since that's also called directly by main.py and by
eval/run_eval.py (whose whole purpose is to catch regressions from
prompt/model changes; a cache sitting inside ask() would silently serve
stale answers to eval reruns instead).

No-ops entirely when AZURE_STORAGE_ACCOUNT_NAME is unset -- e.g. local
Docker dev, which has no managed identity to authenticate with and no Table
Storage to hit. Same empty-config-disables-the-feature pattern as
ADMIN_API_URL in src/graph/remote_graph.py. Every failure (auth, network,
missing entity) is caught and logged, never raised -- a broken cache must
degrade to "always miss," never break /ask.
"""

import hashlib
import json
import logging
import time

from azure.core.exceptions import AzureError, ResourceExistsError, ResourceNotFoundError
from azure.data.tables import TableClient
from azure.identity import DefaultAzureCredential, ManagedIdentityCredential

from src.config import AZURE_CLIENT_ID, AZURE_STORAGE_ACCOUNT_NAME

logger = logging.getLogger(__name__)

CACHE_VERSION = 1  # bump to invalidate every existing entry after a prompt/model change
CACHE_TABLE_NAME = "askcache"
CACHE_PARTITION_KEY = "v1"
CACHE_MAX_AGE_SECONDS = 90 * 24 * 3600  # soft-expiry, checked at read time (Table Storage has no native TTL)

_table_client: TableClient | None = None
_table_client_initialized = False


def _normalize(question: str) -> str:
    return " ".join(question.strip().casefold().split())


def _cache_key(question: str) -> str:
    # sha256 rather than the raw question: PartitionKey/RowKey forbid '/', '\',
    # '#', '?', and control characters, and have a 1KB length limit -- a hash
    # sidesteps both regardless of question content/length.
    return hashlib.sha256(f"{CACHE_VERSION}:{_normalize(question)}".encode("utf-8")).hexdigest()


def _get_table_client() -> TableClient | None:
    global _table_client, _table_client_initialized
    if _table_client_initialized:
        return _table_client
    _table_client_initialized = True  # never retry a broken client on every request

    if not AZURE_STORAGE_ACCOUNT_NAME:
        return None

    try:
        # DefaultAzureCredential doesn't reliably resolve a user-assigned-only
        # managed identity (this app has no system-assigned one) -- Microsoft's
        # documented fix is ManagedIdentityCredential with the UAMI's client ID
        # explicit, so prefer that whenever AZURE_CLIENT_ID is available.
        credential = (
            ManagedIdentityCredential(client_id=AZURE_CLIENT_ID)
            if AZURE_CLIENT_ID
            else DefaultAzureCredential()
        )
        client = TableClient(
            endpoint=f"https://{AZURE_STORAGE_ACCOUNT_NAME}.table.core.windows.net",
            table_name=CACHE_TABLE_NAME,
            credential=credential,
        )
        try:
            client.create_table()
        except ResourceExistsError:
            pass  # already created (by an earlier request, or by infra.yml's Bicep deploy)
        _table_client = client
    except Exception:
        logger.warning("Could not initialize the ask-cache table client; caching disabled", exc_info=True)
        _table_client = None

    return _table_client


def get_cached_answer(question: str) -> dict | None:
    client = _get_table_client()
    if client is None:
        return None

    try:
        entity = client.get_entity(partition_key=CACHE_PARTITION_KEY, row_key=_cache_key(question))
    except ResourceNotFoundError:
        return None
    except AzureError:
        logger.warning("Cache read failed", exc_info=True)
        return None

    if time.time() - entity.get("cached_at", 0) > CACHE_MAX_AGE_SECONDS:
        return None

    return {
        "route": entity.get("route"),
        "answer": entity.get("answer"),
        "sources": json.loads(entity.get("sources") or "[]"),
    }


def set_cached_answer(question: str, result: dict) -> None:
    client = _get_table_client()
    if client is None:
        return

    entity = {
        "PartitionKey": CACHE_PARTITION_KEY,
        "RowKey": _cache_key(question),
        "route": result.get("route") or "",
        "answer": result.get("answer") or "",
        "sources": json.dumps(result.get("sources") or []),
        "cached_at": int(time.time()),
    }
    try:
        client.upsert_entity(entity)
    except AzureError:
        logger.warning("Cache write failed", exc_info=True)
