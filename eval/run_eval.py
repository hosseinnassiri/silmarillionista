"""Run the eval question set through the agent and log route/answer/context.

Input:  data/eval/questions.json
Output: data/eval/results.json
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.agent.graph_app import ask
from src.config import EVAL_DIR

QUESTIONS_PATH = EVAL_DIR / "questions.json"
RESULTS_PATH = EVAL_DIR / "results.json"


def serialize_vector_context(docs) -> list[dict]:
    out = []
    for doc in docs or []:
        meta = doc.metadata
        label = meta["part"] + (
            f" #{meta['chapter_number']}: {meta['chapter_title']}" if meta.get("chapter_number") else ""
        )
        out.append({"chapter": label, "text": doc.page_content})
    return out


def main() -> None:
    questions = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
    results = []

    for i, q in enumerate(questions, 1):
        print(f"[{i}/{len(questions)}] ({q['category']}) {q['question']}")
        try:
            state = ask(q["question"])
            results.append(
                {
                    "id": q["id"],
                    "category": q["category"],
                    "question": q["question"],
                    "expected_route": q["expected_route"],
                    "actual_route": state.get("route"),
                    "answer": state.get("answer"),
                    "sources": state.get("sources"),
                    "vector_context": serialize_vector_context(state.get("vector_context")),
                    "graph_context": state.get("graph_context"),
                    "error": None,
                }
            )
        except Exception as e:
            results.append(
                {
                    "id": q["id"],
                    "category": q["category"],
                    "question": q["question"],
                    "expected_route": q["expected_route"],
                    "actual_route": None,
                    "answer": None,
                    "sources": None,
                    "vector_context": None,
                    "graph_context": None,
                    "error": str(e),
                }
            )
            print(f"  ERROR: {e}")

    RESULTS_PATH.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\nWrote {len(results)} results to {RESULTS_PATH}")


if __name__ == "__main__":
    main()
