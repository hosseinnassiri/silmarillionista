"""Embed chunks.json and persist them to a Chroma collection.

Input:  data/processed/chunks.json (from ingest/chunk.py)
Output: data/processed/chroma_db/ — persisted Chroma collection
"""

import json
import sys
from pathlib import Path

from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from src.config import CHROMA_DIR, CHUNKS_PATH, EMBEDDING_MODEL

COLLECTION_NAME = "silmarillion"


def main() -> None:
    if not CHUNKS_PATH.exists():
        raise FileNotFoundError(f"{CHUNKS_PATH} not found — run ingest/chunk.py first.")

    chunks = json.loads(CHUNKS_PATH.read_text(encoding="utf-8"))
    texts = [c["text"] for c in chunks]
    metadatas = [c["metadata"] for c in chunks]
    ids = [f"{m['part']}-{m['chapter_number']}-{m['chunk_index']}" for m in metadatas]

    embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL)

    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    Chroma.from_texts(
        texts=texts,
        embedding=embeddings,
        metadatas=metadatas,
        ids=ids,
        collection_name=COLLECTION_NAME,
        persist_directory=str(CHROMA_DIR),
    )

    print(f"Embedded {len(texts)} chunks into {CHROMA_DIR} (collection={COLLECTION_NAME!r})")


if __name__ == "__main__":
    main()
