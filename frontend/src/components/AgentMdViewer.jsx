/**
 * AgentMdViewer.jsx – Side-by-side display of Generator and Critic AGENT.MD
 * documents with unified diff highlighting.
 */
import { useState } from 'react';
import { diffLines } from 'diff';
import { X } from 'lucide-react';

const TABS = ['side-by-side', 'diff'];

function DiffView({ generatorMd, criticMd }) {
  const changes = diffLines(generatorMd, criticMd);

  return (
    <div className="overflow-auto h-full font-mono text-xs leading-relaxed p-4">
      <div className="mb-3 flex gap-4 text-xs">
        <span className="flex items-center gap-1">
          <span className="inline-block w-3 h-3 bg-red-900/60 rounded" /> Generator (removed)
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-3 h-3 bg-green-900/60 rounded" /> Critic (added)
        </span>
      </div>
      {changes.map((part, i) => {
        let bg = '';
        let prefix = ' ';
        if (part.added) {
          bg = 'bg-green-900/40 border-l-2 border-green-500';
          prefix = '+';
        } else if (part.removed) {
          bg = 'bg-red-900/40 border-l-2 border-red-500';
          prefix = '-';
        }

        return (
          <div key={i} className={`${bg} px-2`}>
            {part.value.split('\n').map((line, j) =>
              line || j < part.value.split('\n').length - 1 ? (
                <div key={j} className="whitespace-pre-wrap">
                  <span className="text-slate-500 select-none mr-2">{prefix}</span>
                  {line}
                </div>
              ) : null,
            )}
          </div>
        );
      })}
    </div>
  );
}

function MarkdownPanel({ title, content, accentColor }) {
  return (
    <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
      <div className={`px-4 py-2 text-sm font-semibold border-b border-slate-700 ${accentColor}`}>
        {title}
      </div>
      <div className="flex-1 overflow-auto p-4 text-sm leading-relaxed whitespace-pre-wrap font-mono">
        {content}
      </div>
    </div>
  );
}

export default function AgentMdViewer({ generatorMd, criticMd, onClose }) {
  const [tab, setTab] = useState('diff');

  return (
    <div className="flex flex-col h-full bg-slate-900">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-4 py-2 bg-slate-800 border-b border-slate-700 flex-shrink-0">
        <div className="flex items-center gap-4">
          <span className="text-sm font-semibold text-slate-200">📄 AGENT.MD Comparison</span>
          <div className="flex gap-1">
            {TABS.map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`px-3 py-1 rounded text-xs transition-colors ${
                  tab === t
                    ? 'bg-blue-600 text-white'
                    : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                }`}
              >
                {t === 'side-by-side' ? 'Side by Side' : 'Diff View'}
              </button>
            ))}
          </div>
        </div>
        <button
          onClick={onClose}
          className="p-1 rounded hover:bg-slate-700 transition-colors text-slate-400 hover:text-slate-200"
          title="Close"
        >
          <X size={18} />
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden">
        {tab === 'side-by-side' ? (
          <div className="flex h-full divide-x divide-slate-700">
            <MarkdownPanel
              title="🛠️ Generator AGENT.MD"
              content={generatorMd}
              accentColor="text-blue-300"
            />
            <MarkdownPanel
              title="🔍 Critic AGENT.MD"
              content={criticMd}
              accentColor="text-amber-300"
            />
          </div>
        ) : (
          <DiffView generatorMd={generatorMd} criticMd={criticMd} />
        )}
      </div>
    </div>
  );
}
