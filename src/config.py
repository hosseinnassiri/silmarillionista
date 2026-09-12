import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
EVAL_DIR = DATA_DIR / "eval"

CHUNKS_PATH = PROCESSED_DIR / "chunks.json"
CHROMA_DIR = PROCESSED_DIR / "chroma_db"
ILLUSTRATIONS_DIR = PROCESSED_DIR / "illustrations"
ILLUSTRATIONS_MANIFEST = ILLUSTRATIONS_DIR / "manifest.json"

AZURE_OPENAI_API_KEY = os.environ.get("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_ENDPOINT = os.environ.get("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_VERSION = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21")
AZURE_OPENAI_CHAT_DEPLOYMENT = os.environ.get("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-5.5")
AZURE_OPENAI_EMBEDDING_DEPLOYMENT = os.environ.get(
    "AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-large"
)

NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USERNAME = os.environ.get("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD")

# Deployed app's admin Cypher proxy (POST /admin/cypher) — Neo4j has no
# external Bolt ingress in Azure, so local pipeline scripts reach the
# hosted graph through this instead. Only set ADMIN_API_URL when you
# deliberately want a script to target the deployed graph rather than the
# local Docker Neo4j above (see src/graph/remote_graph.py:get_graph()).
# ADMIN_API_KEY doubles as the deployed app's own check on incoming
# requests to that route.
ADMIN_API_URL = os.environ.get("ADMIN_API_URL", "")
ADMIN_API_KEY = os.environ.get("ADMIN_API_KEY", "")

# Table Storage-backed /ask response cache (src/cache.py). Empty by default --
# local Docker dev has no managed identity to authenticate with and no Table
# Storage to hit, so the cache silently no-ops (every question is a miss,
# ask() runs normally) until these are set, which only happens via
# app.bicep's container env in the deployed Container App. AZURE_CLIENT_ID is
# the app's user-assigned identity's client ID -- needed because this
# container app has no system-assigned identity, and DefaultAzureCredential
# alone doesn't reliably resolve a user-assigned-only identity.
AZURE_STORAGE_ACCOUNT_NAME = os.environ.get("AZURE_STORAGE_ACCOUNT_NAME", "")
AZURE_CLIENT_ID = os.environ.get("AZURE_CLIENT_ID", "")

CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
