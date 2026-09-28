"""FastAPI app: serves the chat UI and POST /ask, wrapping src.agent.graph_app.ask().

Includes a best-effort in-memory per-IP rate limiter. This is not the primary
abuse guardrail — that's the Azure OpenAI deployment's own tokens-per-minute
cap, set at deployment time (see README/deploy notes) — but it stops a single
client from hammering the endpoint and keeps response latency fair.
"""

import hmac
import json
import logging
import time
from collections import defaultdict
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from langchain_neo4j import Neo4jGraph
from openai import OpenAIError
from pydantic import BaseModel

from src.agent.graph_app import ask
from src.cache import get_cached_answer, set_cached_answer
from src.config import ADMIN_API_KEY, EVAL_DIR, ILLUSTRATIONS_DIR, NEO4J_PASSWORD, NEO4J_URI, NEO4J_USERNAME
from src.graph.major_events import get_timeline
from src.illustrations.lookup import find_illustrations, get_illustration

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"

RATE_LIMIT_MAX_REQUESTS = 20
RATE_LIMIT_WINDOW_SECONDS = 3600

_request_log: dict[str, list[float]] = defaultdict(list)


def _check_rate_limit(client_ip: str) -> None:
    now = time.monotonic()
    window_start = now - RATE_LIMIT_WINDOW_SECONDS
    recent = [t for t in _request_log[client_ip] if t > window_start]
    if len(recent) >= RATE_LIMIT_MAX_REQUESTS:
        _request_log[client_ip] = recent
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded: max {RATE_LIMIT_MAX_REQUESTS} questions per hour.",
        )
    recent.append(now)
    _request_log[client_ip] = recent


app = FastAPI(title="Silmarillion Agent")


class AskRequest(BaseModel):
    question: str


class AskResponse(BaseModel):
    route: str | None = None
    answer: str | None = None
    sources: list[str] | None = None
    images: list[dict] | None = None


class TimelineEvent(BaseModel):
    id: str
    illustration: dict | None = None


class TimelineEra(BaseModel):
    era: str
    events: list[TimelineEvent]


class TimelineResponse(BaseModel):
    eras: list[TimelineEra]


class CypherRequest(BaseModel):
    query: str
    params: dict = {}


class CypherResponse(BaseModel):
    records: list[dict]


class EvalRequest(BaseModel):
    limit: int | None = None


class EvalResultItem(BaseModel):
    id: str
    category: str
    question: str
    expected_route: str
    actual_route: str | None = None
    answer: str | None = None
    sources: list[str] | None = None
    error: str | None = None


class EvalResponse(BaseModel):
    results: list[EvalResultItem]
    total: int
    errors: int
    route_correct: int
    route_accuracy: float


@app.post("/ask", response_model=AskResponse)
def ask_endpoint(body: AskRequest, request: Request) -> AskResponse:
    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="question must not be empty")
    if len(question) > 500:
        raise HTTPException(status_code=400, detail="question too long (max 500 chars)")

    client_ip = request.client.host if request.client else "unknown"
    _check_rate_limit(client_ip)

    result = get_cached_answer(question)
    if result is None:
        try:
            result = ask(question)
        except OpenAIError as e:
            # OpenAIError is the SDK's actual base exception — APIError (used
            # here previously) only covers call-time failures like content
            # filtering; config-time errors (e.g. missing/invalid credentials,
            # raised directly as OpenAIError by the Azure client constructor)
            # slipped past that narrower catch and hit Starlette's default
            # plain-text 500 handler instead of this one.
            logger.exception("LLM call failed for question: %r", question)
            if "content_filter" in str(e):
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "Azure's content filter blocked this answer (battle/violence content in the "
                        "source text is a common trigger). Try rephrasing the question."
                    ),
                ) from e
            raise HTTPException(
                status_code=502, detail="The language model failed to answer. Please try again."
            ) from e
        set_cached_answer(question, result)

    images: list[dict] = []
    try:
        images = find_illustrations(result.get("answer") or "")
    except Exception:
        # Illustration lookup is cosmetic, not core to the answer — a broken
        # or missing manifest should never turn a good answer into a 500.
        logger.exception("Illustration lookup failed for question: %r", question)

    return AskResponse(
        route=result.get("route"),
        answer=result.get("answer"),
        sources=result.get("sources"),
        images=images or None,
    )


@app.get("/timeline", response_model=TimelineResponse)
def timeline_endpoint() -> TimelineResponse:
    try:
        eras = get_timeline()
    except Exception as e:
        logger.exception("Timeline query failed")
        raise HTTPException(status_code=502, detail="Could not load the timeline. Please try again.") from e

    return TimelineResponse(
        eras=[
            TimelineEra(
                era=era["era"],
                events=[
                    TimelineEvent(id=ev["id"], illustration=get_illustration(ev["id"]))
                    for ev in era["events"]
                ],
            )
            for era in eras
        ]
    )


_admin_graph: Neo4jGraph | None = None


def _get_admin_graph() -> Neo4jGraph:
    global _admin_graph
    if _admin_graph is None:
        _admin_graph = Neo4jGraph(
            url=NEO4J_URI, username=NEO4J_USERNAME, password=NEO4J_PASSWORD, refresh_schema=False
        )
    return _admin_graph


@app.post("/admin/cypher", response_model=CypherResponse)
def admin_cypher(body: CypherRequest, request: Request) -> CypherResponse:
    """Arbitrary Cypher execution against Neo4j, over the app's own (already
    public) HTTPS ingress. This is how local pipeline scripts (extract.py,
    dedupe.py, timeline.py, major_events.py, illustrations/generate.py)
    reach the deployed graph now that Neo4j has no external Bolt ingress —
    see src/graph/remote_graph.py. Gated on a shared secret rather than
    request shape, since these scripts legitimately need full MERGE/DELETE/
    APOC access, not just reads.
    """
    key = request.headers.get("X-Admin-Key", "")
    if not ADMIN_API_KEY or not hmac.compare_digest(key, ADMIN_API_KEY):
        raise HTTPException(status_code=401, detail="unauthorized")

    try:
        records = _get_admin_graph().query(body.query, params=body.params)
    except Exception as e:
        logger.exception("Admin Cypher query failed: %r", body.query)
        raise HTTPException(status_code=502, detail=str(e)) from e

    return CypherResponse(records=records)


@app.post("/admin/eval", response_model=EvalResponse)
def admin_eval(body: EvalRequest, request: Request) -> EvalResponse:
    """Runs data/eval/questions.json through ask() in-process, against
    whatever's actually deployed right now -- the live-deployment equivalent
    of eval/run_eval.py. Added because injecting and running that script via
    `az containerapp exec` proved unreliable (rate-limited/flaky WebSocket
    handshakes on this environment). Calls ask() directly, same as
    run_eval.py, so this never touches the /ask response cache -- eval
    results must always reflect the current code/prompts, never a cached
    answer from before. Gated the same way as /admin/cypher; body.limit lets
    you run a cheap subset before committing to the full (slow, costly) set.
    """
    key = request.headers.get("X-Admin-Key", "")
    if not ADMIN_API_KEY or not hmac.compare_digest(key, ADMIN_API_KEY):
        raise HTTPException(status_code=401, detail="unauthorized")

    questions = json.loads((EVAL_DIR / "questions.json").read_text(encoding="utf-8"))
    if body.limit is not None:
        questions = questions[: body.limit]

    results: list[EvalResultItem] = []
    route_correct = 0
    errors = 0
    for q in questions:
        try:
            state = ask(q["question"])
            actual_route = state.get("route")
            if actual_route == q["expected_route"]:
                route_correct += 1
            results.append(
                EvalResultItem(
                    id=q["id"],
                    category=q["category"],
                    question=q["question"],
                    expected_route=q["expected_route"],
                    actual_route=actual_route,
                    answer=state.get("answer"),
                    sources=state.get("sources"),
                )
            )
        except Exception as e:
            errors += 1
            logger.exception("Eval question failed: %r", q["question"])
            results.append(
                EvalResultItem(
                    id=q["id"],
                    category=q["category"],
                    question=q["question"],
                    expected_route=q["expected_route"],
                    error=str(e),
                )
            )

    total = len(questions)
    return EvalResponse(
        results=results,
        total=total,
        errors=errors,
        route_correct=route_correct,
        route_accuracy=route_correct / total if total else 0.0,
    )


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
if ILLUSTRATIONS_DIR.exists():
    app.mount("/illustrations", StaticFiles(directory=ILLUSTRATIONS_DIR), name="illustrations")
