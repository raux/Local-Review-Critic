/**
 * api.js – Axios instance for the Local-Review-Critic backend.
 *
 * The Vite dev-server proxy routes /chat, /health, and /status to
 * http://localhost:8000, so we only need a relative base URL here.
 */
import axios from 'axios';

const api = axios.create({
  baseURL: '/',
  timeout: 120_000, // 2 minutes – the three-step pipeline can take a while
  headers: { 'Content-Type': 'application/json' },
});

/**
 * Run the Generator → Critic → Synthesis pipeline.
 *
 * @param {string}      prompt       – the user's coding request
 * @param {string|null} lmStudioUrl  – optional base URL override (from the UI config panel)
 * @param {string|null} model        – optional model ID override (from the UI model selector)
 */
export async function runChat(prompt, lmStudioUrl = null, model = null) {
  const payload = { prompt };
  if (lmStudioUrl) payload.lm_studio_url = lmStudioUrl;
  if (model)       payload.model         = model;
  const { data } = await api.post('/chat', payload);
  return data;
}

/**
 * Step 1: Generate initial code from user prompt.
 *
 * @param {string}      prompt       – the user's coding request
 * @param {string|null} lmStudioUrl  – optional base URL override
 * @param {string|null} model        – optional model ID override
 * @returns {Promise<{content: string, reasoning?: string, generated_code: string}>}
 */
export async function generateCode(prompt, lmStudioUrl = null, model = null) {
  const payload = { prompt };
  if (lmStudioUrl) payload.lm_studio_url = lmStudioUrl;
  if (model)       payload.model         = model;
  const { data } = await api.post('/generate', payload);
  return data;
}

/**
 * Step 2: Critique the draft code.
 *
 * @param {string}      draftCode    – the code to review
 * @param {string}      criticType   – "optimistic" or "pessimistic" (also accepts legacy "positive"/"negative")
 * @param {string|null} lmStudioUrl  – optional base URL override
 * @param {string|null} model        – optional model ID override
 * @returns {Promise<{content: string, reasoning?: string}>}
 */
export async function critiqueCode(draftCode, criticType = 'pessimistic', lmStudioUrl = null, model = null) {
  const payload = { draft_code: draftCode, critic_type: criticType };
  if (lmStudioUrl) payload.lm_studio_url = lmStudioUrl;
  if (model)       payload.model         = model;
  const { data } = await api.post('/critique', payload);
  return data;
}

/**
 * Step 3: Synthesize final code incorporating critic feedback.
 *
 * @param {string}      prompt          – the original user request
 * @param {string}      draftCode       – the initial generated code
 * @param {string}      criticComments  – the critic's feedback
 * @param {string|null} lmStudioUrl     – optional base URL override
 * @param {string|null} model           – optional model ID override
 * @returns {Promise<{content: string, reasoning?: string, final_code: string}>}
 */
export async function synthesizeCode(prompt, draftCode, criticComments, lmStudioUrl = null, model = null) {
  const payload = {
    prompt,
    draft_code: draftCode,
    critic_comments: criticComments,
  };
  if (lmStudioUrl) payload.lm_studio_url = lmStudioUrl;
  if (model)       payload.model         = model;
  const { data } = await api.post('/synthesize', payload);
  return data;
}

/**
 * Generate a code diff analysis comparing initial and final code.
 *
 * @param {string}      initialCode  – the original draft code
 * @param {string}      finalCode    – the final synthesized code
 * @param {string|null} lmStudioUrl  – optional base URL override
 * @param {string|null} model        – optional model ID override
 * @returns {Promise<{analysis_md: string}>}
 */
export async function generateAgentMd(initialCode, finalCode, lmStudioUrl = null, model = null) {
  const payload = {
    initial_code: initialCode,
    final_code: finalCode,
  };
  if (lmStudioUrl) payload.lm_studio_url = lmStudioUrl;
  if (model)       payload.model         = model;
  const { data } = await api.post('/generate-agent-md', payload);
  return data;
}

/**
 * Check whether the FastAPI backend itself is alive.
 */
export async function checkBackendHealth() {
  const { data } = await api.get('/health');
  return data;
}

/**
 * Ask the backend whether it can reach LM Studio.
 */
export async function checkServerStatus() {
  const { data } = await api.get('/status');
  return data;
}

// ---------------------------------------------------------------------------
// LM Studio direct helpers (mirrors L-Bonsai's frontend pattern)
// ---------------------------------------------------------------------------
const LM_STUDIO_API_KEY = 'lm-studio';

/**
 * Normalize an LM Studio base URL so it never ends with /v1 or /v1/.
 * This avoids the double-/v1 bug when the caller appends `/v1/models`.
 *
 * @param {string} url – e.g. "http://localhost:1234" or "http://localhost:1234/v1"
 * @returns {string}   – e.g. "http://localhost:1234"
 */
function stripV1Suffix(url) {
  return url.replace(/\/v1\/?$/, '').replace(/\/+$/, '');
}

/**
 * Fetch the list of models currently loaded in LM Studio.
 *
 * @param {string} baseUrl – e.g. "http://localhost:1234" or "http://localhost:1234/v1"
 * @returns {Array<{id: string}>}
 */
export async function fetchLmStudioModels(baseUrl = 'http://localhost:1234') {
  try {
    const resp = await fetch(`${stripV1Suffix(baseUrl)}/v1/models`, {
      headers: { Authorization: `Bearer ${LM_STUDIO_API_KEY}` },
      signal: AbortSignal.timeout(2500),
    });
    if (!resp.ok) return [];
    const data = await resp.json();
    return data.data || [];
  } catch {
    return [];
  }
}

/**
 * Ping LM Studio and return true if it responds.
 *
 * @param {string} baseUrl – e.g. "http://localhost:1234" or "http://localhost:1234/v1"
 */
export async function pingLmStudio(baseUrl = 'http://localhost:1234') {
  try {
    const resp = await fetch(`${stripV1Suffix(baseUrl)}/v1/models`, {
      headers: { Authorization: `Bearer ${LM_STUDIO_API_KEY}` },
      signal: AbortSignal.timeout(2500),
    });
    return resp.ok;
  } catch {
    return false;
  }
}
