"""Query wrapper around the persisted Chroma collection."""

import sys
from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from src.config import CHROMA_DIR, EMBEDDING_MODEL
from src.vectorstore.build_index import COLLECTION_NAME

_store: Chroma | None = None


def _get_store() -> Chroma:
    global _store
    if _store is None:
        if not CHROMA_DIR.exists():
            raise FileNotFoundError(f"{CHROMA_DIR} not found — run vectorstore/build_index.py first.")
        _store = Chroma(
            collection_name=COLLECTION_NAME,
            embedding_function=OpenAIEmbeddings(model=EMBEDDING_MODEL),
            persist_directory=str(CHROMA_DIR),
        )
    return _store


def vector_search(query: str, k: int = 5, filters: dict | None = None) -> list[Document]:
    return _get_store().similarity_search(query, k=k, filter=filters)


if __name__ == "__main__":
    query = sys.argv[1] if len(sys.argv) > 1 else "the creation of the Silmarils"
    for doc in vector_search(query):
        meta = doc.metadata
        label = meta["part"] + (f" #{meta['chapter_number']}: {meta['chapter_title']}" if meta["chapter_number"] else "")
        print(f"--- {label} ---")
        print(doc.page_content[:300].strip())
        print()
