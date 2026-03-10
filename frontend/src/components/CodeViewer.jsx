/**
 * CodeViewer.jsx – Syntax-highlighted code panel with a Copy button.
 */
import { useState } from 'react';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { Copy, Check } from 'lucide-react';

export default function CodeViewer({ code, language = 'python' }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback for environments without clipboard API
      const el = document.createElement('textarea');
      el.value = code;
      document.body.appendChild(el);
      el.select();
      document.execCommand('copy');
      document.body.removeChild(el);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="flex flex-col h-full bg-slate-900">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-4 py-2 bg-slate-800 border-b border-slate-700 flex-shrink-0">
        <span className="text-xs text-slate-400 font-mono">{language}</span>
        {code && (
          <button
            onClick={handleCopy}
            title="Copy code"
            className="flex items-center gap-1 px-2 py-1 rounded text-xs text-slate-300
                       bg-slate-700 hover:bg-slate-600 transition-colors"
          >
            {copied
              ? <><Check size={14} className="text-green-400" /><span className="text-green-400">Copied!</span></>
              : <><Copy size={14} /><span>Copy</span></>
            }
          </button>
        )}
      </div>

      {/* Code area */}
      <div className="flex-1 overflow-auto">
        {code ? (
          <SyntaxHighlighter
            language={language}
            style={vscDarkPlus}
            customStyle={{
              margin: 0,
              padding: '1rem',
              background: 'transparent',
              fontSize: '0.85rem',
              height: '100%',
            }}
            wrapLongLines
          >
            {code}
          </SyntaxHighlighter>
        ) : (
          <div className="h-full flex items-center justify-center text-slate-600 select-none">
            <div className="text-center">
              <p className="text-4xl mb-3">{'</>'}</p>
              <p className="text-sm">Final code will appear here after the pipeline completes.</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
