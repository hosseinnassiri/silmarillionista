"""FastAPI app: serves the chat UI and POST /ask, wrapping src.agent.graph_app.ask().

Includes a best-effort in-memory per-IP rate limiter. This is not the primary
abuse guardrail — that's the Azure OpenAI deployment's own tokens-per-minute
cap, set at deployment time (see README/deploy notes) — but it stops a single
client from hammering the endpoint and keeps response latency fair.
"""

import logging
import time
from collections import defaultdict
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from openai import OpenAIError
from pydantic import BaseModel

from src.agent.graph_app import ask
from src.config import ILLUSTRATIONS_DIR
from src.illustrations.lookup import find_illustrations

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


@app.post("/ask", response_model=AskResponse)
def ask_endpoint(body: AskRequest, request: Request) -> AskResponse:
    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="question must not be empty")
    if len(question) > 500:
        raise HTTPException(status_code=400, detail="question too long (max 500 chars)")

    client_ip = request.client.host if request.client else "unknown"
    _check_rate_limit(client_ip)

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
        raise HTTPException(status_code=502, detail="The language model failed to answer. Please try again.") from e

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


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
if ILLUSTRATIONS_DIR.exists():
    app.mount("/illustrations", StaticFiles(directory=ILLUSTRATIONS_DIR), name="illustrations")
