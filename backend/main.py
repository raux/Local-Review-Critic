"""
main.py – FastAPI entry point for Local-Review-Critic.
"""
from __future__ import annotations

import os
import logging

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

app = FastAPI(title="Local-Review-Critic API", version="1.0.0")

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
# Startup health-check
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def check_lm_studio_connection() -> None:
    """Verify that LM Studio is reachable when the server starts."""
    health_url = LM_STUDIO_BASE_URL.rstrip("/v1").rstrip("/") + "/v1/models"
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


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------
class ChatRequest(BaseModel):
    prompt: str


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
    health_url = LM_STUDIO_BASE_URL.rstrip("/v1").rstrip("/") + "/v1/models"
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
    """
    if not request.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt must not be empty.")

    # Verify LM Studio is reachable before committing to a long pipeline call
    health_url = LM_STUDIO_BASE_URL.rstrip("/v1").rstrip("/") + "/v1/models"
    try:
        async with httpx.AsyncClient(timeout=5.0) as http:
            resp = await http.get(health_url)
            resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=503,
            detail=f"Local Server Offline: LM Studio is not reachable. ({exc})",
        ) from exc

    try:
        model = get_model()
        client = get_client()
        result = run_pipeline(client, model, request.prompt)
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
