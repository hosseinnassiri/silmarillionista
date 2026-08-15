"""FastAPI app: serves the chat UI and POST /ask, wrapping src.agent.graph_app.ask().

Includes a best-effort in-memory per-IP rate limiter. This is not the primary
abuse guardrail — that's the Azure OpenAI deployment's own tokens-per-minute
cap, set at deployment time (see README/deploy notes) — but it stops a single
client from hammering the endpoint and keeps response latency fair.
"""

import time
from collections import defaultdict
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.agent.graph_app import ask

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


@app.post("/ask", response_model=AskResponse)
def ask_endpoint(body: AskRequest, request: Request) -> AskResponse:
    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="question must not be empty")
    if len(question) > 500:
        raise HTTPException(status_code=400, detail="question too long (max 500 chars)")

    client_ip = request.client.host if request.client else "unknown"
    _check_rate_limit(client_ip)

    result = ask(question)
    return AskResponse(route=result.get("route"), answer=result.get("answer"), sources=result.get("sources"))


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
