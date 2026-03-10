/**
 * App.jsx – Main application layout.
 *
 * Split-pane view:
 *   Left  (40%) → LmStudioConfig header + Chat list + message input
 *   Right (60%) → LoadingStates (while running) + CodeViewer
 */
import { useState, useCallback, useRef } from 'react';
import Chat          from './components/Chat.jsx';
import CodeViewer    from './components/CodeViewer.jsx';
import LoadingStates from './components/LoadingStates.jsx';
import LmStudioConfig from './components/LmStudioConfig.jsx';
import { runChat }   from './api.js';
import { Send }      from 'lucide-react';

// Pipeline phase sequence used by LoadingStates
const PHASES = ['generating', 'reviewing', 'applying'];

export default function App() {
  const [messages, setMessages]     = useState([]);
  const [finalCode, setFinalCode]   = useState('');
  const [phase, setPhase]           = useState(null);   // null | 'generating' | 'reviewing' | 'applying'
  const [error, setError]           = useState('');
  const [input, setInput]           = useState('');
  const [lmConfig, setLmConfig]     = useState({ lmStudioUrl: '', model: '' });

  // Ref so we can simulate phase progression during the (blocking) pipeline call
  const phaseTimer = useRef(null);

  const handleConfigChange = useCallback((cfg) => {
    setLmConfig(cfg);
  }, []);

  const startPhaseAnimation = () => {
    let idx = 0;
    setPhase(PHASES[0]);
    phaseTimer.current = setInterval(() => {
      idx += 1;
      if (idx < PHASES.length) {
        setPhase(PHASES[idx]);
      }
    }, 8000); // advance every ~8 s
  };

  const stopPhaseAnimation = () => {
    clearInterval(phaseTimer.current);
    setPhase(null);
  };

  const handleSend = async () => {
    const prompt = input.trim();
    if (!prompt || phase) return;

    setInput('');
    setError('');
    setMessages(prev => [...prev, { role: 'user', content: prompt }]);
    startPhaseAnimation();

    try {
      const data = await runChat(
        prompt,
        lmConfig.lmStudioUrl || null,
        lmConfig.model        || null,
      );

      // Add all pipeline messages to the chat history
      for (const msg of data.chat_history) {
        setMessages(prev => [...prev, msg]);
      }

      setFinalCode(data.final_code);
    } catch (err) {
      const detail =
        err?.response?.data?.detail ||
        err?.message ||
        'Unknown error';

      const isOffline = detail.toLowerCase().includes('offline') ||
                        detail.toLowerCase().includes('reachable') ||
                        err?.response?.status === 503;

      const displayMsg = isOffline
        ? '⚠️ Local Server Offline – make sure LM Studio is running and a model is loaded.'
        : `❌ Error: ${detail}`;

      setError(displayMsg);
      setMessages(prev => [...prev, { role: 'generator', content: displayMsg }]);
    } finally {
      stopPhaseAnimation();
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const isLoading = phase !== null;

  return (
    <div className="flex flex-col h-screen bg-slate-900 text-slate-100">
      {/* ── App header ────────────────────────────────────────────────── */}
      <header className="flex items-center gap-3 px-5 py-3 bg-slate-800 border-b border-slate-700 flex-shrink-0">
        <span className="text-lg font-semibold tracking-tight">🔍 Local Review Critic</span>
        <span className="text-xs text-slate-500 hidden sm:block">
          Generator → Critic → Synthesis · powered by LM Studio
        </span>
      </header>

      {/* ── LM Studio connection bar (from L-Bonsai) ──────────────────── */}
      <LmStudioConfig onConfigChange={handleConfigChange} />

      {/* ── Main split pane ───────────────────────────────────────────── */}
      <div className="flex flex-1 overflow-hidden">

        {/* Left pane – 40% – chat */}
        <div className="flex flex-col w-2/5 border-r border-slate-700 overflow-hidden">
          <div className="flex-1 overflow-y-auto">
            <Chat messages={messages} loading={isLoading} />
          </div>

          {/* Input area */}
          <div className="flex-shrink-0 p-3 border-t border-slate-700 bg-slate-800">
            {error && (
              <p className="text-xs text-red-400 mb-2 px-1">{error}</p>
            )}
            <div className="flex gap-2 items-end">
              <textarea
                rows={3}
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={isLoading}
                placeholder="Ask for a code solution… (Enter to send, Shift+Enter for new line)"
                className="flex-1 resize-none rounded-lg bg-slate-900 border border-slate-600
                           text-sm text-slate-100 placeholder-slate-500 px-3 py-2
                           focus:outline-none focus:border-blue-500
                           disabled:opacity-50 disabled:cursor-not-allowed"
              />
              <button
                onClick={handleSend}
                disabled={isLoading || !input.trim()}
                className="flex-shrink-0 p-3 rounded-lg bg-blue-600 hover:bg-blue-500
                           disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                title="Send"
              >
                <Send size={18} />
              </button>
            </div>
          </div>
        </div>

        {/* Right pane – 60% – code viewer */}
        <div className="flex flex-col flex-1 overflow-hidden">
          {isLoading && (
            <div className="p-4 flex-shrink-0">
              <LoadingStates phase={phase} />
            </div>
          )}
          <div className="flex-1 overflow-hidden">
            <CodeViewer code={finalCode} language="python" />
          </div>
        </div>

      </div>
    </div>
  );
}
