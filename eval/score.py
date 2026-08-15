"""Score eval results: routing accuracy + LLM-assisted answer quality.

Input:  data/eval/results.json (from run_eval.py)
Output: data/eval/scored_results.json, plus a printed summary.
"""

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.config import EVAL_DIR
from src.llm import get_chat_llm

RESULTS_PATH = EVAL_DIR / "results.json"
SCORED_PATH = EVAL_DIR / "scored_results.json"

# Regression gate thresholds. Routing accuracy has fluctuated 79-93% across
# recent runs on unrelated changes (router-LLM non-determinism), and 1-2
# quality<=2 failures recur on genuinely hard cases (quote_01, between_01)
# without being new regressions -- these thresholds are set to catch a real
# break (e.g. the MENTIONS-pollution bug, which would fail this badly) while
# tolerating that observed noise band.
MIN_ROUTING_ACCURACY = 0.75
MAX_LOW_QUALITY_COUNT = 3

JUDGE_SYSTEM = """\
You are grading an answer from a RAG+graph agent about J.R.R. Tolkien's The \
Silmarillion. Rate the answer 1-5 given the question, category, and the \
context that was actually available to it:

5 = fully correct, grounded in the given context, appropriately cited
4 = correct but missing minor detail
3 = partially correct or incomplete, not actively wrong
2 = meaningfully wrong or missing something important it should have caught
1 = incorrect, hallucinated beyond the context, or fails to say "not covered" \
when the context doesn't actually answer the question

Special rule for category "out_of_scope": these questions are deliberately NOT \
answerable from The Silmarillion. A high score REQUIRES the answer to say so \
explicitly rather than guessing or fabricating — confidently answering an \
out_of_scope question is a 1, no matter how plausible it sounds.
"""


class Verdict(BaseModel):
    score: Literal[1, 2, 3, 4, 5]
    reason: str


def judge(llm, result: dict) -> Verdict:
    context_summary = "Vector context chapters: " + ", ".join(
        c["chapter"] for c in (result.get("vector_context") or [])
    )
    graph_context = result.get("graph_context")
    if graph_context and graph_context.get("records"):
        context_summary += f"\nGraph records: {graph_context['records']}"
    if not (result.get("vector_context") or (graph_context and graph_context.get("records"))):
        context_summary = "(no context was retrieved)"

    prompt = (
        f"Category: {result['category']}\n"
        f"Question: {result['question']}\n"
        f"Context available to the agent:\n{context_summary}\n\n"
        f"Agent's answer:\n{result.get('answer')}\n"
    )
    return llm.invoke([SystemMessage(content=JUDGE_SYSTEM), HumanMessage(content=prompt)])


def main() -> None:
    if not RESULTS_PATH.exists():
        raise FileNotFoundError(f"{RESULTS_PATH} not found — run eval/run_eval.py first.")

    results = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    judge_llm = get_chat_llm().with_structured_output(Verdict)

    scored = []
    route_correct = 0
    scores = []
    by_category = defaultdict(lambda: {"route_correct": 0, "total": 0, "scores": []})

    for r in results:
        if r.get("error"):
            scored.append({**r, "route_correct": False, "quality_score": None, "quality_reason": r["error"]})
            by_category[r["category"]]["total"] += 1
            continue

        route_ok = r["actual_route"] == r["expected_route"]
        verdict: Verdict = judge(judge_llm, r)

        scored.append(
            {**r, "route_correct": route_ok, "quality_score": verdict.score, "quality_reason": verdict.reason}
        )

        route_correct += int(route_ok)
        scores.append(verdict.score)
        cat = by_category[r["category"]]
        cat["total"] += 1
        cat["route_correct"] += int(route_ok)
        cat["scores"].append(verdict.score)

        print(f"  {r['id']:12s} route={'OK ' if route_ok else 'MISS'} quality={verdict.score}")

    SCORED_PATH.write_text(json.dumps(scored, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    n = len(results)
    print(f"\n=== Summary ({n} questions) ===")
    print(f"Routing accuracy: {route_correct}/{n} = {100 * route_correct / n:.0f}%")
    if scores:
        print(f"Avg answer quality: {sum(scores) / len(scores):.2f}/5")

    print("\nBy category:")
    for cat, stats in sorted(by_category.items()):
        avg_q = sum(stats["scores"]) / len(stats["scores"]) if stats["scores"] else float("nan")
        print(f"  {cat:20s} route {stats['route_correct']}/{stats['total']}   quality {avg_q:.1f}/5")

    print("\nFailures worth reviewing (route mismatch or quality <= 2):")
    for r in scored:
        if r.get("error") or not r["route_correct"] or (r["quality_score"] or 5) <= 2:
            print(f"  [{r['id']}] {r['question']}")
            print(f"    expected_route={r['expected_route']} actual_route={r.get('actual_route')} "
                  f"quality={r.get('quality_score')}")
            print(f"    reason: {r.get('quality_reason')}")

    print(f"\nFull results: {SCORED_PATH}")

    routing_accuracy = route_correct / n
    low_quality_count = sum(1 for r in scored if (r.get("quality_score") or 5) <= 2 or r.get("error"))

    routing_ok = routing_accuracy >= MIN_ROUTING_ACCURACY
    quality_ok = low_quality_count <= MAX_LOW_QUALITY_COUNT

    print("\n=== Regression gate ===")
    print(
        f"  Routing accuracy:  {'PASS' if routing_ok else 'FAIL'} "
        f"({100 * routing_accuracy:.0f}% >= {100 * MIN_ROUTING_ACCURACY:.0f}% required)"
    )
    print(
        f"  Low-quality count: {'PASS' if quality_ok else 'FAIL'} "
        f"({low_quality_count} <= {MAX_LOW_QUALITY_COUNT} allowed)"
    )

    if not (routing_ok and quality_ok):
        print("\nGATE: FAIL")
        sys.exit(1)
    print("\nGATE: PASS")


if __name__ == "__main__":
    main()
