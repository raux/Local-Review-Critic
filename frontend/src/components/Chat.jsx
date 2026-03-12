/**
 * Chat.jsx – Chat bubble list with auto-scroll to the bottom.
 *
 * Each message in `messages` has:
 *   { role: 'user' | 'generator' | 'critic' | 'thinking' | 'system', content: string }
 */
import { useEffect, useRef } from 'react';

const ROLE_META = {
  user:      { label: 'You',       bg: 'bg-blue-900',   text: 'text-blue-200',   align: 'items-end'   },
  generator: { label: 'Generator', bg: 'bg-slate-700',  text: 'text-slate-100',  align: 'items-start' },
  critic:    { label: 'Critic',    bg: 'bg-amber-900',  text: 'text-amber-100',  align: 'items-start' },
  thinking:  { label: '🤔 Thinking', bg: 'bg-purple-900', text: 'text-purple-100', align: 'items-start' },
  system:    { label: 'System',     bg: 'bg-slate-600',  text: 'text-slate-200',  align: 'items-start' },
};

function ChatBubble({ role, content }) {
  const meta = ROLE_META[role] || ROLE_META.generator;

  return (
    <div className={`flex flex-col gap-1 ${meta.align}`}>
      <span className="text-xs text-slate-500 px-1">{meta.label}</span>
      <div className={`max-w-[90%] px-4 py-2 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap ${meta.bg} ${meta.text}`}>
        {content}
      </div>
    </div>
  );
}

export default function Chat({ messages, loading }) {
  const bottomRef = useRef(null);

  // Auto-scroll to bottom whenever messages change
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  return (
    <div className="flex flex-col gap-4 p-4 overflow-y-auto h-full">
      {messages.length === 0 && !loading && (
        <div className="m-auto text-center text-slate-500 text-sm select-none">
          <p className="text-2xl mb-2">💬</p>
          <p>Ask for any code and the agents will generate, review, and refine it.</p>
        </div>
      )}

      {messages.map((msg, i) => (
        <ChatBubble key={i} role={msg.role} content={msg.content} />
      ))}

      {/* Sentinel element for auto-scroll */}
      <div ref={bottomRef} />
    </div>
  );
}
