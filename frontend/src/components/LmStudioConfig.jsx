/**
 * LmStudioConfig.jsx
 *
 * Ported from raux/L-Bonsai frontend/main.js, extended to support both
 * LM Studio and Ollama as local AI server providers.
 *
 * Renders a header bar with:
 *  - Provider selector (LM Studio / Ollama)
 *  - Server URL input (persisted to localStorage, default changes with provider)
 *  - Model selector dropdown (auto-populated from the selected server, persisted)
 *  - Connect button with 🔌 / ⏳ / ✓ states
 *  - Connection status badge (● Connected / ○ Disconnected / ⏳ Connecting)
 *  - Inline error / success message
 *
 * Auto-polls the selected server every 5 seconds.
 * Calls onConfigChange({ lmStudioUrl, model, provider }) whenever any value changes.
 */
import { useEffect, useRef, useState, useCallback } from 'react';
import { fetchModels, pingServer, PROVIDER_DEFAULTS } from '../api.js';

const LS_URL_KEY      = 'lmStudioUrl';
const LS_MODEL_KEY    = 'selectedModel';
const LS_PROVIDER_KEY = 'selectedProvider';
const POLL_MS         = 5000;

const PROVIDER_LABELS = {
  lm_studio: 'LM Studio',
  ollama:    'Ollama',
};

export default function LmStudioConfig({ onConfigChange }) {
  const [provider, setProvider] = useState(
    () => localStorage.getItem(LS_PROVIDER_KEY) || 'lm_studio',
  );
  const [url, setUrl]             = useState(
    () => localStorage.getItem(LS_URL_KEY) || PROVIDER_DEFAULTS.lm_studio,
  );
  const [models, setModels]       = useState([]);
  const [model, setModel]         = useState(
    () => localStorage.getItem(LS_MODEL_KEY) || '',
  );
  const [status, setStatus]       = useState('disconnected'); // 'connecting' | 'connected' | 'disconnected'
  const [message, setMessage]     = useState({ text: '', type: '' });
  const pollRef                   = useRef(null);
  const prevConnected             = useRef(false);
  // Keep a ref to the latest url so the polling interval always uses the
  // current value without needing to be torn-down and re-created on every change.
  const urlRef                    = useRef(url);

  // -------------------------------------------------------------------------
  // Helpers
  // -------------------------------------------------------------------------
  const showMessage = useCallback((text, type = 'error') => {
    setMessage({ text, type });
    if (type === 'success') {
      setTimeout(() => setMessage({ text: '', type: '' }), 3000);
    }
  }, []);

  const populateModels = useCallback(async (baseUrl) => {
    const list = await fetchModels(baseUrl);
    setModels(list);

    if (list.length === 0) return;

    const saved = localStorage.getItem(LS_MODEL_KEY);
    const chosen = (saved && list.some(m => m.id === saved))
      ? saved
      : list[0].id;

    setModel(chosen);
    localStorage.setItem(LS_MODEL_KEY, chosen);
  }, []);

  const doHealthCheck = useCallback(async (baseUrl) => {
    // Basic URL format validation
    try {
      new URL(baseUrl.startsWith('http') ? baseUrl : `http://${baseUrl}`);
    } catch {
      setStatus('disconnected');
      showMessage('Invalid URL format. Please check the server URL.', 'error');
      return false;
    }

    const ok = await pingServer(baseUrl);
    if (ok) {
      setStatus('connected');
      showMessage(''); // clear any error
    } else {
      setStatus('disconnected');
    }
    return ok;
  }, [showMessage]);

  // -------------------------------------------------------------------------
  // Initial connection + polling (mirrors L-Bonsai's IIFE + setInterval)
  // -------------------------------------------------------------------------
  useEffect(() => {
    let cancelled = false;

    const init = async () => {
      setStatus('connecting');
      const ok = await doHealthCheck(urlRef.current);
      if (!cancelled && ok) {
        await populateModels(urlRef.current);
        prevConnected.current = true;
      } else {
        prevConnected.current = false;
      }
    };
    init();

    // Use urlRef so the interval always reads the latest URL without being
    // recreated every time the user edits the input field.
    pollRef.current = setInterval(async () => {
      const wasConnected = prevConnected.current;
      const ok = await doHealthCheck(urlRef.current);
      if (ok && !wasConnected) {
        await populateModels(urlRef.current);
      }
      prevConnected.current = ok;
    }, POLL_MS);

    return () => {
      cancelled = true;
      clearInterval(pollRef.current);
    };
  }, [doHealthCheck, populateModels]); // stable callbacks – no stale-closure risk

  // Notify parent whenever url, model, or provider changes
  useEffect(() => {
    onConfigChange?.({ lmStudioUrl: url, model, provider });
  }, [url, model, provider, onConfigChange]);

  // -------------------------------------------------------------------------
  // Event handlers
  // -------------------------------------------------------------------------
  const handleProviderChange = (e) => {
    const val = e.target.value;
    setProvider(val);
    localStorage.setItem(LS_PROVIDER_KEY, val);

    // Auto-update URL when switching providers if still at the old default
    const oldDefault = PROVIDER_DEFAULTS[provider] || PROVIDER_DEFAULTS.lm_studio;
    const newDefault = PROVIDER_DEFAULTS[val] || PROVIDER_DEFAULTS.lm_studio;
    const currentUrl = urlRef.current;
    if (!currentUrl || currentUrl === oldDefault) {
      setUrl(newDefault);
      urlRef.current = newDefault;
      localStorage.setItem(LS_URL_KEY, newDefault);
    }

    // Reset models list and reconnect to new provider URL
    setModels([]);
    setModel('');
    setStatus('connecting');
  };

  const handleUrlChange = (e) => {
    const val = e.target.value.trim();
    setUrl(val);
    urlRef.current = val;
    localStorage.setItem(LS_URL_KEY, val);
  };

  const handleModelChange = (e) => {
    const val = e.target.value;
    setModel(val);
    localStorage.setItem(LS_MODEL_KEY, val);
  };

  const handleConnect = async () => {
    setStatus('connecting');
    showMessage('');
    const ok = await doHealthCheck(url);
    if (ok) {
      await populateModels(url);
      showMessage(`Successfully connected to ${PROVIDER_LABELS[provider] || provider}!`, 'success');
    } else {
      showMessage(`Could not connect. Is ${PROVIDER_LABELS[provider] || provider} running?`, 'error');
    }
    prevConnected.current = ok;
  };

  // -------------------------------------------------------------------------
  // Derived UI state (mirrors L-Bonsai button / badge logic)
  // -------------------------------------------------------------------------
  const providerLabel = PROVIDER_LABELS[provider] || provider;
  const badgeIcon = { connected: '●', disconnected: '○', connecting: '⏳' }[status];
  const badgeLabel = { connected: 'Connected', disconnected: 'Disconnected', connecting: 'Connecting...' }[status];
  const badgeColor = {
    connected:    'text-green-400',
    disconnected: 'text-slate-400',
    connecting:   'text-amber-400',
  }[status];

  const btnLabel = { connected: '✓ Connected', disconnected: '🔌 Connect', connecting: '⏳ Connecting...' }[status];
  const btnColor = {
    connected:    'bg-green-700 hover:bg-green-600',
    disconnected: 'bg-slate-700 hover:bg-slate-600',
    connecting:   'bg-amber-700 cursor-not-allowed',
  }[status];

  const msgColor = { error: 'text-red-400', success: 'text-green-400', info: 'text-blue-400' }[message.type] || '';

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------
  return (
    <div className="flex flex-col gap-1 px-4 py-2 bg-slate-800 border-b border-slate-700">
      <div className="flex flex-wrap items-center gap-3">
        {/* Status badge */}
        <span className={`text-xs font-mono ${badgeColor}`}>
          {badgeIcon} {providerLabel} {badgeLabel}
        </span>

        {/* Provider selector */}
        <select
          value={provider}
          onChange={handleProviderChange}
          className="bg-slate-900 text-slate-200 text-xs border border-slate-600 rounded
                     px-2 py-1 focus:outline-none focus:border-blue-500"
          title="Select local AI provider"
        >
          <option value="lm_studio">LM Studio</option>
          <option value="ollama">Ollama</option>
        </select>

        {/* URL input */}
        <input
          type="text"
          value={url}
          onChange={handleUrlChange}
          placeholder={PROVIDER_DEFAULTS[provider] || 'http://localhost:1234'}
          className="flex-1 min-w-[180px] max-w-xs bg-slate-900 text-slate-200 text-xs
                     border border-slate-600 rounded px-2 py-1 focus:outline-none
                     focus:border-blue-500"
        />

        {/* Model selector */}
        <select
          value={model}
          onChange={handleModelChange}
          disabled={models.length === 0}
          className="bg-slate-900 text-slate-200 text-xs border border-slate-600 rounded
                     px-2 py-1 focus:outline-none focus:border-blue-500
                     disabled:opacity-50 disabled:cursor-not-allowed max-w-[220px]"
        >
          {models.length === 0
            ? <option value="">Select model…</option>
            : models.map(m => (
                <option key={m.id} value={m.id}>{m.id}</option>
              ))
          }
        </select>

        {/* Connect button */}
        <button
          onClick={handleConnect}
          disabled={status === 'connecting'}
          className={`text-xs px-3 py-1 rounded text-white transition-colors ${btnColor}`}
        >
          {btnLabel}
        </button>
      </div>

      {/* Inline message */}
      {message.text && (
        <p className={`text-xs ${msgColor}`}>{message.text}</p>
      )}
    </div>
  );
}

