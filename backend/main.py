"""
main.py – FastAPI entry point for Local-Review-Critic.
"""
from __future__ import annotations

import os
import logging
import urllib.parse
from contextlib import asynccontextmanager

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from pydantic import BaseModel

from agents import run_pipeline

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

LM_STUDIO_BASE_URL: str = os.getenv("LM_STUDIO_BASE_URL", "http://localhost:1234/v1")
LM_STUDIO_MODEL: str = os.getenv("LM_STUDIO_MODEL", "")

# Hostnames / IP ranges that are allowed as the LM Studio base URL.
# LM Studio is always local, so we restrict to loopback addresses only
# to prevent SSRF when the frontend passes lm_studio_url in the request body.
_ALLOWED_HOSTS: frozenset[str] = frozenset({
    "localhost",
    "127.0.0.1",
    "::1",
})


def _validate_lm_studio_url(url: str) -> str:
    """
    Ensure *url* points only to a loopback address (localhost / 127.0.0.1 / ::1).
    Returns the normalised URL string or raises HTTPException 400.
    """
    try:
        parsed = urllib.parse.urlparse(url)
        host = parsed.hostname or ""
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Invalid LM Studio URL: {exc}") from exc

    if host not in _ALLOWED_HOSTS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"LM Studio URL host '{host}' is not allowed. "
                "Only localhost / 127.0.0.1 / ::1 are permitted."
            ),
        )
    return url


# ---------------------------------------------------------------------------
# Startup health-check (lifespan context manager – preferred over on_event)
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(application: FastAPI):
    """Verify that LM Studio is reachable when the server starts."""
    health_url = LM_STUDIO_BASE_URL.rstrip("/") + "/models"
    try:
        async with httpx.AsyncClient(timeout=5.0) as http:
            resp = await http.get(health_url)
            resp.raise_for_status()
        logger.info("LM Studio is reachable at %s", LM_STUDIO_BASE_URL)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "LM Studio not reachable at startup (%s). "
            "The server will still start but AI calls will fail until "
            "LM Studio is running.",
            exc,
        )
    yield  # application runs here


app = FastAPI(title="Local-Review-Critic API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Shared OpenAI-compatible client (lazy – resolved at first request if model
# was not pre-configured in .env)
# ---------------------------------------------------------------------------
_client: OpenAI | None = None
_resolved_model: str = ""


def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(base_url=LM_STUDIO_BASE_URL, api_key="lm-studio")
    return _client


def get_model() -> str:
    global _resolved_model
    if _resolved_model:
        return _resolved_model
    if LM_STUDIO_MODEL:
        _resolved_model = LM_STUDIO_MODEL
        return _resolved_model
    # Fetch the first available model from LM Studio
    client = get_client()
    models = client.models.list()
    model_ids = [m.id for m in models.data]
    if not model_ids:
        raise HTTPException(
            status_code=503,
            detail="LM Studio returned no available models.",
        )
    _resolved_model = model_ids[0]
    logger.info("Auto-selected model: %s", _resolved_model)
    return _resolved_model


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------
class ChatRequest(BaseModel):
    prompt: str
    lm_studio_url: str | None = None  # overrides .env when provided by the frontend
    model: str | None = None          # overrides auto-selected model when provided


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatResponse(BaseModel):
    chat_history: list[ChatMessage]
    critic_comments: str
    final_code: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/health")
async def health() -> dict:
    """Simple liveness probe."""
    return {"status": "ok"}


@app.get("/status")
async def status() -> dict:
    """Check whether LM Studio is currently reachable."""
    health_url = LM_STUDIO_BASE_URL.rstrip("/") + "/models"
    try:
        async with httpx.AsyncClient(timeout=5.0) as http:
            resp = await http.get(health_url)
            resp.raise_for_status()
        return {"lm_studio": "online", "base_url": LM_STUDIO_BASE_URL}
    except Exception as exc:  # noqa: BLE001
        return {"lm_studio": "offline", "error": str(exc)}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """
    Run the Generator → Critic → Synthesis pipeline and return the results.
    Optionally accepts lm_studio_url and model from the frontend (e.g. from
    the LM Studio Config panel) to override the server defaults.
    """
    if not request.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt must not be empty.")

    # Resolve the effective LM Studio base URL and model for this request.
    # Frontend-supplied values (from the LmStudioConfig panel) take priority.
    # Validate user-supplied URL to prevent SSRF (must be loopback only), then
    # reconstruct from the integer port so no user-controlled string flows into
    # the outgoing HTTP request.
    if request.lm_studio_url:
        _validate_lm_studio_url(request.lm_studio_url)
        parsed = urllib.parse.urlparse(request.lm_studio_url)
        port = int(parsed.port) if parsed.port else 1234  # integer – not user-controlled string
        effective_url = f"http://localhost:{port}/v1"
    else:
        effective_url = LM_STUDIO_BASE_URL.rstrip("/")
        if not effective_url.endswith("/v1"):
            effective_url = effective_url + "/v1"

    # Verify LM Studio is reachable before committing to a long pipeline call
    health_url = effective_url + "/models"
    try:
        async with httpx.AsyncClient(timeout=5.0) as http:
            resp = await http.get(
                health_url,
                headers={"Authorization": "Bearer lm-studio"},
            )
            resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=503,
            detail=f"Local Server Offline: LM Studio is not reachable. ({exc})",
        ) from exc

    try:
        # Build a per-request client if the URL differs from the global default
        if effective_url != LM_STUDIO_BASE_URL.rstrip("/"):
            req_client = OpenAI(base_url=effective_url, api_key="lm-studio")
        else:
            req_client = get_client()

        # Resolve model: prefer request-supplied > env/auto-selected
        if request.model:
            req_model = request.model
        else:
            # Use module-level auto-selected model (or resolve it now)
            req_model = get_model()

        result = run_pipeline(req_client, req_model, request.prompt)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Pipeline error: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Pipeline error: {exc}",
        ) from exc

    return ChatResponse(
        chat_history=[ChatMessage(**m) for m in result["chat_history"]],
        critic_comments=result["critic_comments"],
        final_code=result["final_code"],
    )
