/**
 * LmStudioConfig.jsx
 *
 * Ported from raux/L-Bonsai frontend/main.js.
 *
 * Renders a header bar with:
 *  - LM Studio URL input (persisted to localStorage)
 *  - Model selector dropdown (auto-populated from LM Studio, persisted)
 *  - Connect button with 🔌 / ⏳ / ✓ states
 *  - Connection status badge (● Connected / ○ Disconnected / ⏳ Connecting)
 *  - Inline error / success message
 *
 * Auto-polls LM Studio every 5 seconds.
 * Calls onConfigChange({ lmStudioUrl, model }) whenever either value changes.
 */
import { useEffect, useRef, useState, useCallback } from 'react';
import { fetchLmStudioModels, pingLmStudio } from '../api.js';

const LS_URL_KEY   = 'lmStudioUrl';
const LS_MODEL_KEY = 'selectedModel';
const POLL_MS      = 5000;

export default function LmStudioConfig({ onConfigChange }) {
  const [url, setUrl]             = useState(
    () => localStorage.getItem(LS_URL_KEY) || 'http://192.168.144.25:1234',
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
    const list = await fetchLmStudioModels(baseUrl);
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
      showMessage('Invalid URL format. Please check the LM Studio URL.', 'error');
      return false;
    }

    const ok = await pingLmStudio(baseUrl);
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

  // Notify parent whenever url or model changes
  useEffect(() => {
    onConfigChange?.({ lmStudioUrl: url, model });
  }, [url, model, onConfigChange]);

  // -------------------------------------------------------------------------
  // Event handlers
  // -------------------------------------------------------------------------
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
      showMessage('Successfully connected to LM Studio!', 'success');
    } else {
      showMessage('Could not connect. Is LM Studio running?', 'error');
    }
    prevConnected.current = ok;
  };

  // -------------------------------------------------------------------------
  // Derived UI state (mirrors L-Bonsai button / badge logic)
  // -------------------------------------------------------------------------
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
          {badgeIcon} LM Studio {badgeLabel}
        </span>

        {/* URL input */}
        <input
          type="text"
          value={url}
          onChange={handleUrlChange}
          placeholder="http://192.168.144.25:1234"
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

        {/* Retrieve Models button */}
        <button
          onClick={() => populateModels(url)}
          disabled={status === 'connecting'}
          className="text-xs px-3 py-1 rounded text-white bg-slate-700 hover:bg-slate-600
                     disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          ↻ Models
        </button>

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
