"""Chunk each chapter/part record into ~500-token pieces with metadata.

Input:  data/processed/chapters.json (from clean_text.py)
Output: data/processed/chunks.json — list of {"text": str, "metadata": {...}}
"""

import json
import sys
from pathlib import Path

import tiktoken
from langchain_text_splitters import RecursiveCharacterTextSplitter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from src.config import CHUNK_OVERLAP, CHUNK_SIZE, CHUNKS_PATH, PROCESSED_DIR

_ENCODING = tiktoken.get_encoding("cl100k_base")


def _token_len(text: str) -> int:
    return len(_ENCODING.encode(text))


def main() -> None:
    chapters_path = PROCESSED_DIR / "chapters.json"
    if not chapters_path.exists():
        raise FileNotFoundError(f"{chapters_path} not found — run clean_text.py first.")

    records = json.loads(chapters_path.read_text(encoding="utf-8"))

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        length_function=_token_len,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    chunks = []
    for record in records:
        part = record["part"]
        chapter_number = record["chapter_number"]
        chapter_title = record["chapter_title"]

        pieces = splitter.split_text(record["text"])
        for i, piece in enumerate(pieces):
            chunks.append(
                {
                    "text": piece,
                    "metadata": {
                        "part": part,
                        "chapter_number": chapter_number,
                        "chapter_title": chapter_title,
                        "chunk_index": i,
                    },
                }
            )

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    CHUNKS_PATH.write_text(json.dumps(chunks, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Wrote {len(chunks)} chunks to {CHUNKS_PATH}")
    lengths = [_token_len(c["text"]) for c in chunks]
    if lengths:
        print(f"  min/avg/max tokens: {min(lengths)}/{sum(lengths)//len(lengths)}/{max(lengths)}")


if __name__ == "__main__":
    main()
