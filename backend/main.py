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

from agents import (
    run_pipeline, generate_code, critique_code, synthesize_code,
    generate_agent_md, GENERATOR_SYSTEM, POSITIVE_CRITIC_SYSTEM,
    NEGATIVE_CRITIC_SYSTEM,
)

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


async def _resolve_client_and_model(lm_studio_url: str | None, model: str | None) -> tuple[OpenAI, str]:
    """
    Helper function to resolve the OpenAI client and model for a request.
    Validates the LM Studio URL, checks connectivity, and returns the client and model.
    """
    # Resolve the effective LM Studio base URL and model for this request.
    # Frontend-supplied values take priority over server defaults.
    # Validate user-supplied URL to prevent SSRF (must be loopback only)
    if lm_studio_url:
        _validate_lm_studio_url(lm_studio_url)
        parsed = urllib.parse.urlparse(lm_studio_url)
        port = int(parsed.port) if parsed.port else 1234  # integer – not user-controlled string
        effective_url = f"http://localhost:{port}/v1"
    else:
        effective_url = LM_STUDIO_BASE_URL.rstrip("/")
        if not effective_url.endswith("/v1"):
            effective_url = effective_url + "/v1"

    # Verify LM Studio is reachable before committing to a call
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

    # Build a per-request client if the URL differs from the global default
    if effective_url != LM_STUDIO_BASE_URL.rstrip("/"):
        req_client = OpenAI(base_url=effective_url, api_key="lm-studio")
    else:
        req_client = get_client()

    # Resolve model: prefer request-supplied > env/auto-selected
    if model:
        req_model = model
    else:
        req_model = get_model()

    return req_client, req_model


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------
class ChatRequest(BaseModel):
    prompt: str
    lm_studio_url: str | None = None  # overrides .env when provided by the frontend
    model: str | None = None          # overrides auto-selected model when provided


class GenerateRequest(BaseModel):
    prompt: str
    lm_studio_url: str | None = None
    model: str | None = None


class CritiqueRequest(BaseModel):
    draft_code: str
    critic_type: str = "negative"  # "positive" or "negative"
    lm_studio_url: str | None = None
    model: str | None = None


class SynthesizeRequest(BaseModel):
    prompt: str
    draft_code: str
    critic_comments: str
    lm_studio_url: str | None = None
    model: str | None = None


class ChatMessage(BaseModel):
    role: str
    content: str
    reasoning: str | None = None  # Optional thinking/reasoning from model


class StepResponse(BaseModel):
    content: str
    reasoning: str | None = None  # Optional thinking/reasoning from model


class SynthesizeResponse(BaseModel):
    content: str
    reasoning: str | None = None
    final_code: str


class ChatResponse(BaseModel):
    chat_history: list[ChatMessage]
    critic_comments: str
    final_code: str


class AgentMdRequest(BaseModel):
    generator_output: str
    critic_output: str
    lm_studio_url: str | None = None
    model: str | None = None


class AgentMdResponse(BaseModel):
    generator_md: str
    critic_md: str


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


@app.post("/generate", response_model=StepResponse)
async def generate(request: GenerateRequest) -> StepResponse:
    """
    Step 1: Generate initial code from user prompt.
    Returns the generated code and optional reasoning/thinking from the model.
    """
    if not request.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt must not be empty.")

    try:
        req_client, req_model = await _resolve_client_and_model(
            request.lm_studio_url, request.model
        )
        result = generate_code(req_client, req_model, request.prompt)
        return StepResponse(**result)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Generate error: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Generate error: {exc}",
        ) from exc


@app.post("/critique", response_model=StepResponse)
async def critique(request: CritiqueRequest) -> StepResponse:
    """
    Step 2: Critique the draft code.
    Accepts critic_type: "positive" (strengths-focused) or "negative" (issues-focused).
    Returns the review/feedback and optional reasoning/thinking from the model.
    """
    if not request.draft_code.strip():
        raise HTTPException(status_code=400, detail="Draft code must not be empty.")
    if request.critic_type not in ("positive", "negative"):
        raise HTTPException(status_code=400, detail="critic_type must be 'positive' or 'negative'.")

    try:
        req_client, req_model = await _resolve_client_and_model(
            request.lm_studio_url, request.model
        )
        result = critique_code(req_client, req_model, request.draft_code, critic_type=request.critic_type)
        return StepResponse(**result)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Critique error: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Critique error: {exc}",
        ) from exc


@app.post("/synthesize", response_model=SynthesizeResponse)
async def synthesize(request: SynthesizeRequest) -> SynthesizeResponse:
    """
    Step 3: Synthesize final code incorporating critic feedback.
    Returns the final code, reasoning, and extracted code without markdown fences.
    """
    if not request.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt must not be empty.")
    if not request.draft_code.strip():
        raise HTTPException(status_code=400, detail="Draft code must not be empty.")
    if not request.critic_comments.strip():
        raise HTTPException(status_code=400, detail="Critic comments must not be empty.")

    try:
        req_client, req_model = await _resolve_client_and_model(
            request.lm_studio_url, request.model
        )
        result = synthesize_code(
            req_client, req_model, request.prompt, request.draft_code, request.critic_comments
        )
        return SynthesizeResponse(**result)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Synthesize error: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Synthesize error: {exc}",
        ) from exc


@app.post("/generate-agent-md", response_model=AgentMdResponse)
async def generate_agent_md_endpoint(request: AgentMdRequest) -> AgentMdResponse:
    """
    Generate AGENT.MD documents for both the Generator and Critic agents.
    Returns markdown descriptions based on each agent's system prompt and sample output.
    """
    if not request.generator_output.strip():
        raise HTTPException(status_code=400, detail="Generator output must not be empty.")
    if not request.critic_output.strip():
        raise HTTPException(status_code=400, detail="Critic output must not be empty.")

    try:
        req_client, req_model = await _resolve_client_and_model(
            request.lm_studio_url, request.model
        )
        gen_md = generate_agent_md(
            req_client, req_model, "Generator", GENERATOR_SYSTEM, request.generator_output
        )
        positive_critic_md = generate_agent_md(
            req_client, req_model, "Positive Critic", POSITIVE_CRITIC_SYSTEM, request.critic_output
        )
        negative_critic_md = generate_agent_md(
            req_client, req_model, "Negative Critic", NEGATIVE_CRITIC_SYSTEM, request.critic_output
        )
        return AgentMdResponse(
            generator_md=gen_md["content"],
            critic_md=positive_critic_md["content"] + "\n\n---\n\n" + negative_critic_md["content"],
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("AGENT.MD generation error: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"AGENT.MD generation error: {exc}",
        ) from exc


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """
    Run the Generator → Critic → Synthesis pipeline and return the results.
    This endpoint maintains backward compatibility with the original implementation.
    For step-by-step execution, use the /generate, /critique, and /synthesize endpoints.
    """
    if not request.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt must not be empty.")

    try:
        req_client, req_model = await _resolve_client_and_model(
            request.lm_studio_url, request.model
        )
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
