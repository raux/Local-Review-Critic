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
import AgentMdViewer from './components/AgentMdViewer.jsx';
import { generateCode, critiqueCode, synthesizeCode, generateAgentMd } from './api.js';
import { Send } from 'lucide-react';

// Pipeline phase sequence used by LoadingStates
const PHASES = ['generating', 'reviewing', 'applying'];

export default function App() {
  const [messages, setMessages]     = useState([]);
  const [finalCode, setFinalCode]   = useState('');
  const [phase, setPhase]           = useState(null);   // null | 'generating' | 'reviewing' | 'applying'
  const [error, setError]           = useState('');
  const [input, setInput]           = useState('');
  const [lmConfig, setLmConfig]     = useState({ lmStudioUrl: '', model: '' });

  // Step-by-step execution state
  const [currentStep, setCurrentStep]       = useState(0);  // 0=initial, 1=generated, 2=critiqued, 3=synthesized
  const [userPrompt, setUserPrompt]         = useState('');
  const [draftCode, setDraftCode]           = useState('');
  const [criticComments, setCriticComments] = useState('');
  const [positiveCriticComments, setPositiveCriticComments] = useState('');
  const [negativeCriticComments, setNegativeCriticComments] = useState('');
  const [isProcessing, setIsProcessing]     = useState(false);

  // AGENT.MD generation state
  const [generatorMd, setGeneratorMd]       = useState('');
  const [criticMd, setCriticMd]             = useState('');
  const [showAgentMd, setShowAgentMd]       = useState(false);
  const [isGeneratingMd, setIsGeneratingMd] = useState(false);

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
    if (!prompt || isProcessing) return;

    setInput('');
    setError('');
    setUserPrompt(prompt);
    setMessages(prev => [...prev, { role: 'user', content: prompt }]);
    setCurrentStep(0);

    // Start with step 1: Generate
    await handleGenerate(prompt);
  };

  const handleGenerate = async (prompt = userPrompt) => {
    setIsProcessing(true);
    setPhase('generating');
    setError('');

    try {
      const data = await generateCode(
        prompt,
        lmConfig.lmStudioUrl || null,
        lmConfig.model        || null,
      );

      setDraftCode(data.generated_code);
      setMessages(prev => [...prev, { role: 'generator', content: data.content, reasoning: data.reasoning }]);

      // If there's reasoning/thinking, add it to chat
      if (data.reasoning) {
        setMessages(prev => [...prev, { role: 'thinking', content: data.reasoning }]);
      }

      setCurrentStep(1);
      setFinalCode(data.generated_code);  // Show extracted code only
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
      setIsProcessing(false);
      setPhase(null);
    }
  };

  const handleCritique = async (criticType = 'negative') => {
    if (!draftCode || isProcessing) return;

    setIsProcessing(true);
    setPhase('reviewing');
    setError('');

    const role = criticType === 'positive' ? 'positive_critic' : 'negative_critic';

    try {
      const data = await critiqueCode(
        draftCode,
        criticType,
        lmConfig.lmStudioUrl || null,
        lmConfig.model        || null,
      );

      if (criticType === 'positive') {
        setPositiveCriticComments(data.content);
      } else {
        setNegativeCriticComments(data.content);
      }
      // Build combined critic comments for synthesis.
      // Use data.content for the current critic type (fresh value) and
      // existing state for the other type (unchanged, already up-to-date).
      const newPositive = criticType === 'positive' ? data.content : positiveCriticComments;
      const newNegative = criticType === 'negative' ? data.content : negativeCriticComments;
      const combined = [
        newPositive ? `Positive feedback:\n${newPositive}` : '',
        newNegative ? `Negative feedback:\n${newNegative}` : '',
      ].filter(Boolean).join('\n\n');
      setCriticComments(combined);

      setMessages(prev => [...prev, { role, content: data.content, reasoning: data.reasoning }]);

      // If there's reasoning/thinking, add it to chat
      if (data.reasoning) {
        setMessages(prev => [...prev, { role: 'thinking', content: data.reasoning }]);
      }

      setCurrentStep(2);
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
      setMessages(prev => [...prev, { role, content: displayMsg }]);
    } finally {
      setIsProcessing(false);
      setPhase(null);
    }
  };

  const handleSynthesize = async () => {
    if (!draftCode || !criticComments || isProcessing) return;

    setIsProcessing(true);
    setPhase('applying');
    setError('');

    try {
      const data = await synthesizeCode(
        userPrompt,
        draftCode,
        criticComments,
        lmConfig.lmStudioUrl || null,
        lmConfig.model        || null,
      );

      setMessages(prev => [...prev, { role: 'generator', content: data.content, reasoning: data.reasoning }]);

      // If there's reasoning/thinking, add it to chat
      if (data.reasoning) {
        setMessages(prev => [...prev, { role: 'thinking', content: data.reasoning }]);
      }

      setFinalCode(data.final_code);
      setCurrentStep(3);
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
      setIsProcessing(false);
      setPhase(null);
    }
  };

  const handleGenerateAgentMd = async () => {
    if (!draftCode || !criticComments || isGeneratingMd) return;

    setIsGeneratingMd(true);
    setError('');

    try {
      const data = await generateAgentMd(
        draftCode,
        criticComments,
        lmConfig.lmStudioUrl || null,
        lmConfig.model        || null,
      );

      setGeneratorMd(data.generator_md);
      setCriticMd(data.critic_md);
      setShowAgentMd(true);
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
        : `❌ Error generating AGENT.MD: ${detail}`;

      setError(displayMsg);
    } finally {
      setIsGeneratingMd(false);
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
          Generator → Positive Critic ↔ Negative Critic → Synthesis · powered by LM Studio
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
                disabled={isLoading || currentStep > 0}
                placeholder="Ask for a code solution… (Enter to send, Shift+Enter for new line)"
                className="flex-1 resize-none rounded-lg bg-slate-900 border border-slate-600
                           text-sm text-slate-100 placeholder-slate-500 px-3 py-2
                           focus:outline-none focus:border-blue-500
                           disabled:opacity-50 disabled:cursor-not-allowed"
              />
              <button
                onClick={handleSend}
                disabled={isLoading || !input.trim() || currentStep > 0}
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

          {/* Step control buttons */}
          {currentStep > 0 && currentStep < 3 && (
            <div className="p-4 flex-shrink-0 bg-slate-800 border-b border-slate-700">
              <div className="flex gap-3 items-center flex-wrap">
                {currentStep === 1 && (
                  <>
                    <button
                      onClick={() => handleCritique('positive')}
                      disabled={isProcessing}
                      className="px-4 py-2 rounded-lg bg-green-700 hover:bg-green-600
                                 disabled:opacity-40 disabled:cursor-not-allowed transition-colors
                                 text-sm font-medium"
                    >
                      {isProcessing ? '⏳ Processing...' : '👍 Positive Review'}
                    </button>
                    <button
                      onClick={() => handleCritique('negative')}
                      disabled={isProcessing}
                      className="px-4 py-2 rounded-lg bg-red-700 hover:bg-red-600
                                 disabled:opacity-40 disabled:cursor-not-allowed transition-colors
                                 text-sm font-medium"
                    >
                      {isProcessing ? '⏳ Processing...' : '👎 Negative Review'}
                    </button>
                    <span className="text-xs text-slate-400">
                      Choose a positive or negative critic to review the generated code
                    </span>
                  </>
                )}

                {currentStep === 2 && (
                  <>
                    <button
                      onClick={() => handleCritique('positive')}
                      disabled={isProcessing}
                      className="px-4 py-2 rounded-lg bg-green-700 hover:bg-green-600
                                 disabled:opacity-40 disabled:cursor-not-allowed transition-colors
                                 text-sm font-medium"
                    >
                      {isProcessing ? '⏳ Processing...' : '👍 Positive Review'}
                    </button>
                    <button
                      onClick={() => handleCritique('negative')}
                      disabled={isProcessing}
                      className="px-4 py-2 rounded-lg bg-red-700 hover:bg-red-600
                                 disabled:opacity-40 disabled:cursor-not-allowed transition-colors
                                 text-sm font-medium"
                    >
                      {isProcessing ? '⏳ Processing...' : '👎 Negative Review'}
                    </button>
                    <button
                      onClick={handleSynthesize}
                      disabled={isProcessing}
                      className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500
                                 disabled:opacity-40 disabled:cursor-not-allowed transition-colors
                                 text-sm font-medium"
                    >
                      {isProcessing ? '⏳ Processing...' : '✨ Apply Changes'}
                    </button>
                    <span className="text-xs text-slate-400">
                      Add more reviews or apply changes
                    </span>
                  </>
                )}
              </div>
            </div>
          )}

          {currentStep === 3 && (
            <div className="p-4 flex-shrink-0 bg-slate-800 border-b border-slate-700">
              <div className="flex gap-3 items-center flex-wrap">
                <span className="text-sm text-green-400 font-medium">✓ Pipeline Complete</span>
                <button
                  onClick={() => {
                    setFinalCode(draftCode);
                    setCriticComments('');
                    setPositiveCriticComments('');
                    setNegativeCriticComments('');
                    setCurrentStep(1);
                    setGeneratorMd('');
                    setCriticMd('');
                    setShowAgentMd(false);
                    setMessages(prev => [...prev, { role: 'system', content: '↩️ Reverted to original draft code.' }]);
                  }}
                  className="px-4 py-2 rounded-lg bg-orange-600 hover:bg-orange-500
                             transition-colors text-sm font-medium"
                >
                  ↩️ Revert to Draft
                </button>
                <button
                  onClick={handleGenerateAgentMd}
                  disabled={isGeneratingMd || isProcessing}
                  className="px-4 py-2 rounded-lg bg-purple-600 hover:bg-purple-500
                             disabled:opacity-40 disabled:cursor-not-allowed transition-colors
                             text-sm font-medium"
                >
                  {isGeneratingMd ? '⏳ Generating…' : '📄 Generate AGENT.MD'}
                </button>
                {generatorMd && criticMd && (
                  <button
                    onClick={() => setShowAgentMd(prev => !prev)}
                    className={`px-4 py-2 rounded-lg transition-colors text-sm font-medium ${
                      showAgentMd
                        ? 'bg-slate-600 hover:bg-slate-500'
                        : 'bg-indigo-600 hover:bg-indigo-500'
                    }`}
                  >
                    {showAgentMd ? '🖥️ Show Code' : '📄 Show AGENT.MD'}
                  </button>
                )}
                <button
                  onClick={() => {
                    setCurrentStep(0);
                    setUserPrompt('');
                    setDraftCode('');
                    setCriticComments('');
                    setPositiveCriticComments('');
                    setNegativeCriticComments('');
                    setFinalCode('');
                    setMessages([]);
                    setGeneratorMd('');
                    setCriticMd('');
                    setShowAgentMd(false);
                  }}
                  className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500
                             transition-colors text-sm font-medium"
                >
                  Start New Request
                </button>
              </div>
            </div>
          )}

          <div className="flex-1 overflow-hidden">
            {showAgentMd && generatorMd && criticMd ? (
              <AgentMdViewer
                generatorMd={generatorMd}
                criticMd={criticMd}
                onClose={() => setShowAgentMd(false)}
              />
            ) : (
              <CodeViewer code={finalCode} language="python" />
            )}
          </div>
        </div>

      </div>
    </div>
  );
}
