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
    generate_agent_md,
)

load_dotenv()

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Keep noisy third-party loggers at WARNING so our debug output stays readable
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.INFO)

LM_STUDIO_BASE_URL: str = os.getenv("LM_STUDIO_BASE_URL", "http://localhost:1234/v1")
LM_STUDIO_MODEL: str = os.getenv("LM_STUDIO_MODEL", "")

OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")

# Hostnames / IP ranges that are allowed as the LM Studio base URL.
# LM Studio is always local, so we restrict to loopback addresses only
# to prevent SSRF when the frontend passes lm_studio_url in the request body.
_ALLOWED_HOSTS: frozenset[str] = frozenset({
    "localhost",
    "127.0.0.1",
    "::1",
})


def _normalize_base_url(url: str) -> str:
    """
    Ensure *url* ends with ``/v1`` so that appending ``/models`` or creating
    an OpenAI client always produces the correct LM Studio API path.

    Accepts any of:
      - ``http://localhost:1234``
      - ``http://localhost:1234/``
      - ``http://localhost:1234/v1``
      - ``http://localhost:1234/v1/``
    """
    url = url.rstrip("/")
    if not url.endswith("/v1"):
        url = url + "/v1"
    return url


def _validate_lm_studio_url(url: str) -> str:
    """
    Ensure *url* points only to a loopback address (localhost / 127.0.0.1 / ::1).
    Accepts URLs for both LM Studio and Ollama.
    Returns the normalised URL string or raises HTTPException 400.
    """
    try:
        parsed = urllib.parse.urlparse(url)
        host = parsed.hostname or ""
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Invalid server URL: {exc}") from exc

    if host not in _ALLOWED_HOSTS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Server URL host '{host}' is not allowed. "
                "Only localhost / 127.0.0.1 / ::1 are permitted."
            ),
        )
    return url


# ---------------------------------------------------------------------------
# Startup health-check (lifespan context manager – preferred over on_event)
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(application: FastAPI):
    """Verify that at least one local AI server (LM Studio or Ollama) is reachable when the server starts."""
    logger.debug("Configured LM_STUDIO_BASE_URL = %s", LM_STUDIO_BASE_URL)
    logger.debug("Configured LM_STUDIO_MODEL    = %s", LM_STUDIO_MODEL or "(auto-detect)")
    logger.debug("Configured OLLAMA_BASE_URL     = %s", OLLAMA_BASE_URL)

    async def _check_server(base_url: str, label: str) -> bool:
        health_url = base_url.rstrip("/") + "/models"
        logger.debug("Startup health-check (%s) → GET %s", label, health_url)
        try:
            async with httpx.AsyncClient(timeout=5.0) as http:
                resp = await http.get(health_url)
                logger.debug(
                    "Startup health-check (%s) response: status=%s", label, resp.status_code
                )
                resp.raise_for_status()
            logger.info("%s is reachable at %s", label, base_url)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "%s not reachable at startup (%s: %s).",
                label,
                type(exc).__name__,
                exc,
            )
            return False

    lm_ok = await _check_server(LM_STUDIO_BASE_URL, "LM Studio")
    ollama_ok = await _check_server(OLLAMA_BASE_URL, "Ollama")

    if not lm_ok and not ollama_ok:
        logger.warning(
            "Neither LM Studio nor Ollama is reachable at startup. "
            "The server will still start but AI calls will fail until a local AI server is running."
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
        _client = OpenAI(base_url=_normalize_base_url(LM_STUDIO_BASE_URL), api_key="lm-studio")
        logger.debug("Creating default OpenAI client → base_url=%s", LM_STUDIO_BASE_URL)
        _client = OpenAI(base_url=LM_STUDIO_BASE_URL, api_key="lm-studio")
    return _client


def get_model() -> str:
    global _resolved_model
    if _resolved_model:
        return _resolved_model
    if LM_STUDIO_MODEL:
        _resolved_model = LM_STUDIO_MODEL
        logger.debug("Using model from LM_STUDIO_MODEL env: %s", _resolved_model)
        return _resolved_model
    # Fetch the first available model from the default server
    logger.debug("No model configured – fetching available models from local server…")
    client = get_client()
    models = client.models.list()
    model_ids = [m.id for m in models.data]
    logger.debug("Models returned by local server: %s", model_ids)
    if not model_ids:
        raise HTTPException(
            status_code=503,
            detail="Local AI server returned no available models.",
        )
    _resolved_model = model_ids[0]
    logger.info("Auto-selected model: %s", _resolved_model)
    return _resolved_model


async def _resolve_client_and_model(
    lm_studio_url: str | None,
    model: str | None,
    provider: str | None = None,
) -> tuple[OpenAI, str]:
    """
    Helper function to resolve the OpenAI client and model for a request.
    Supports both LM Studio and Ollama (any OpenAI-compatible local server).
    Validates the URL, checks connectivity, and returns the client and model.

    Provider resolution order:
      1. If *lm_studio_url* is supplied by the frontend, use it (works for both LM Studio & Ollama).
      2. If *provider* is "ollama" and no URL override given, use OLLAMA_BASE_URL from env.
      3. Otherwise fall back to LM_STUDIO_BASE_URL from env.
    """
    logger.debug(
        "Resolving client & model – lm_studio_url=%r, model=%r, provider=%r",
        lm_studio_url,
        model,
        provider,
    )

    if lm_studio_url:
        logger.debug("Frontend supplied server URL=%s – validating…", lm_studio_url)
        _validate_lm_studio_url(lm_studio_url)
        parsed = urllib.parse.urlparse(lm_studio_url)
        # Use the supplied port when present; fall back to provider-appropriate default
        if parsed.port:
            port = int(parsed.port)  # integer – not user-controlled string
        elif provider == "ollama":
            port = 11434
        else:
            port = 1234
        effective_url = f"http://localhost:{port}/v1"
        logger.debug("Effective URL after normalisation: %s", effective_url)
    elif provider == "ollama":
        effective_url = _normalize_base_url(OLLAMA_BASE_URL)
        logger.debug("Using Ollama default URL: %s", effective_url)
    else:
        effective_url = _normalize_base_url(LM_STUDIO_BASE_URL)
        logger.debug("Using LM Studio default URL: %s", effective_url)

    # Verify the local server is reachable before committing to a call
    health_url = effective_url + "/models"
    logger.debug("Connectivity check → GET %s (timeout=5s)", health_url)
    try:
        async with httpx.AsyncClient(timeout=5.0) as http:
            resp = await http.get(
                health_url,
                headers={"Authorization": "Bearer lm-studio"},
            )
            logger.debug(
                "Connectivity check response: status=%s, content-length=%s",
                resp.status_code,
                resp.headers.get("content-length", "unknown"),
            )
            resp.raise_for_status()
    except httpx.ConnectError as exc:
        logger.error(
            "Cannot connect to local AI server at %s – is it running? (%s: %s)",
            effective_url,
            type(exc).__name__,
            exc,
        )
        raise HTTPException(
            status_code=503,
            detail=(
                f"Local Server Offline: Cannot connect to local AI server at {effective_url}. "
                f"Make sure LM Studio or Ollama is running. ({exc})"
            ),
        ) from exc
    except httpx.TimeoutException as exc:
        logger.error(
            "Timeout connecting to local AI server at %s after 5s (%s: %s)",
            effective_url,
            type(exc).__name__,
            exc,
        )
        raise HTTPException(
            status_code=503,
            detail=(
                f"Local Server Offline: Local AI server at {effective_url} did not respond "
                f"within 5 seconds. ({exc})"
            ),
        ) from exc
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Unexpected error reaching local AI server at %s: %s: %s",
            effective_url,
            type(exc).__name__,
            exc,
        )
        raise HTTPException(
            status_code=503,
            detail=f"Local Server Offline: Local AI server is not reachable. ({exc})",
        ) from exc

    # Build a per-request client if the URL differs from the global default
    if effective_url != _normalize_base_url(LM_STUDIO_BASE_URL):
        logger.debug(
            "URL differs from global default – creating per-request client for %s",
            effective_url,
        )
        req_client = OpenAI(base_url=effective_url, api_key="lm-studio")
    else:
        req_client = get_client()

    # Resolve model: prefer request-supplied > env/auto-selected
    if model:
        req_model = model
        logger.debug("Using request-supplied model: %s", req_model)
    else:
        req_model = get_model()
        logger.debug("Using resolved model: %s", req_model)

    logger.debug("Client & model resolved → model=%s, base_url=%s", req_model, effective_url)
    return req_client, req_model


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------
class ChatRequest(BaseModel):
    prompt: str
    lm_studio_url: str | None = None  # overrides .env when provided by the frontend
    model: str | None = None          # overrides auto-selected model when provided
    provider: str | None = None       # "lm_studio" | "ollama"; None falls back to LM Studio


class GenerateRequest(BaseModel):
    prompt: str
    lm_studio_url: str | None = None
    model: str | None = None
    provider: str | None = None       # "lm_studio" | "ollama"; None falls back to LM Studio


class CritiqueRequest(BaseModel):
    draft_code: str
    critic_type: str = "pessimistic"  # "optimistic" or "pessimistic" (also accepts legacy "positive"/"negative")
    lm_studio_url: str | None = None
    model: str | None = None
    provider: str | None = None       # "lm_studio" | "ollama"; None falls back to LM Studio


class SynthesizeRequest(BaseModel):
    prompt: str
    draft_code: str
    critic_comments: str
    lm_studio_url: str | None = None
    model: str | None = None
    provider: str | None = None       # "lm_studio" | "ollama"; None falls back to LM Studio


class ChatMessage(BaseModel):
    role: str
    content: str
    reasoning: str | None = None  # Optional thinking/reasoning from model


class StepResponse(BaseModel):
    content: str
    reasoning: str | None = None  # Optional thinking/reasoning from model


class GenerateResponse(BaseModel):
    content: str
    reasoning: str | None = None
    generated_code: str


class SynthesizeResponse(BaseModel):
    content: str
    reasoning: str | None = None
    final_code: str


class ChatResponse(BaseModel):
    chat_history: list[ChatMessage]
    critic_comments: str
    final_code: str


class AgentMdRequest(BaseModel):
    initial_code: str
    final_code: str
    lm_studio_url: str | None = None
    model: str | None = None
    provider: str | None = None       # "lm_studio" | "ollama"; None falls back to LM Studio


class AgentMdResponse(BaseModel):
    analysis_md: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/health")
async def health() -> dict:
    """Simple liveness probe."""
    return {"status": "ok"}


@app.get("/status")
async def status() -> dict:
    """Check whether LM Studio and/or Ollama is currently reachable."""

    async def _ping(base_url: str, label: str) -> dict:
        health_url = base_url.rstrip("/") + "/models"
        logger.debug("Status check (%s) → GET %s", label, health_url)
        try:
            async with httpx.AsyncClient(timeout=5.0) as http:
                resp = await http.get(health_url)
                logger.debug("Status check (%s) response: status=%s", label, resp.status_code)
                resp.raise_for_status()
            logger.info("Status check: %s is online at %s", label, base_url)
            return {"status": "online", "base_url": base_url}
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Status check: %s is offline (%s: %s)",
                label,
                type(exc).__name__,
                exc,
            )
            return {"status": "offline", "error": type(exc).__name__}

    lm_studio_status = await _ping(LM_STUDIO_BASE_URL, "LM Studio")
    ollama_status = await _ping(OLLAMA_BASE_URL, "Ollama")

    return {
        "lm_studio": lm_studio_status,
        "ollama": ollama_status,
    }


@app.post("/generate", response_model=GenerateResponse)
async def generate(request: GenerateRequest) -> GenerateResponse:
    """
    Step 1: Generate initial code from user prompt.

    Returns:
      - content: full model response (natural language + code blocks) shown in chat
      - reasoning: optional thinking/reasoning from the model
      - generated_code: extracted code without markdown fences for the code canvas
    """
    if not request.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt must not be empty.")

    logger.debug(
        "POST /generate – prompt length=%d, lm_studio_url=%r, model=%r, provider=%r",
        len(request.prompt),
        request.lm_studio_url,
        request.model,
        request.provider,
    )

    try:
        req_client, req_model = await _resolve_client_and_model(
            request.lm_studio_url, request.model, request.provider
        )
        result = generate_code(req_client, req_model, request.prompt)
        logger.debug("POST /generate completed – response content length=%d", len(result.get("content", "")))
        return GenerateResponse(**result)
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
    Accepts critic_type: "optimistic" (strengths-focused) or "pessimistic" (issues-focused, defensive programming).
    Also accepts legacy values: "positive" → "optimistic", "negative" → "pessimistic".
    Returns the review/feedback and optional reasoning/thinking from the model.
    """
    if not request.draft_code.strip():
        raise HTTPException(status_code=400, detail="Draft code must not be empty.")
    if request.critic_type not in ("optimistic", "pessimistic", "positive", "negative"):
        raise HTTPException(
            status_code=400,
            detail="critic_type must be 'optimistic', 'pessimistic' (or legacy 'positive', 'negative')."
        )

    logger.debug(
        "POST /critique – critic_type=%s, draft length=%d, lm_studio_url=%r, model=%r, provider=%r",
        request.critic_type,
        len(request.draft_code),
        request.lm_studio_url,
        request.model,
        request.provider,
    )

    try:
        req_client, req_model = await _resolve_client_and_model(
            request.lm_studio_url, request.model, request.provider
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

    logger.debug(
        "POST /synthesize – prompt length=%d, draft length=%d, comments length=%d, "
        "lm_studio_url=%r, model=%r, provider=%r",
        len(request.prompt),
        len(request.draft_code),
        len(request.critic_comments),
        request.lm_studio_url,
        request.model,
        request.provider,
    )

    try:
        req_client, req_model = await _resolve_client_and_model(
            request.lm_studio_url, request.model, request.provider
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
    Generate a code diff analysis comparing initial draft code to final synthesized code.
    Returns a markdown report highlighting changes, improvements, and quality enhancements.
    """
    if not request.initial_code.strip():
        raise HTTPException(status_code=400, detail="Initial code must not be empty.")
    if not request.final_code.strip():
        raise HTTPException(status_code=400, detail="Final code must not be empty.")

    logger.debug(
        "POST /generate-agent-md – initial_code length=%d, final_code length=%d, "
        "lm_studio_url=%r, model=%r, provider=%r",
        len(request.initial_code),
        len(request.final_code),
        request.lm_studio_url,
        request.model,
        request.provider,
    )

    try:
        req_client, req_model = await _resolve_client_and_model(
            request.lm_studio_url, request.model, request.provider
        )
        analysis = generate_agent_md(
            req_client, req_model, request.initial_code, request.final_code
        )
        return AgentMdResponse(
            analysis_md=analysis["content"]
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Code diff analysis generation error: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"Code diff analysis generation error: {exc}",
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

    logger.debug(
        "POST /chat – prompt length=%d, lm_studio_url=%r, model=%r, provider=%r",
        len(request.prompt),
        request.lm_studio_url,
        request.model,
        request.provider,
    )

    try:
        req_client, req_model = await _resolve_client_and_model(
            request.lm_studio_url, request.model, request.provider
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
