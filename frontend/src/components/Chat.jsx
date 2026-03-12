/**
 * Chat.jsx – Chat bubble list with auto-scroll to the bottom.
 *
 * Each message in `messages` has:
 *   { role: 'user' | 'generator' | 'optimistic_critic' | 'pessimistic_critic' | 'thinking' | 'system', content: string }
 */
import { useEffect, useRef } from 'react';

const ROLE_META = {
  user:                { label: 'You',                          bg: 'bg-blue-900',   text: 'text-blue-200',   align: 'items-end'   },
  generator:           { label: 'Generator',                    bg: 'bg-slate-700',  text: 'text-slate-100',  align: 'items-start' },
  optimistic_critic:   { label: '✨ Optimistic Coding',         bg: 'bg-green-900',  text: 'text-green-100',  align: 'items-start' },
  pessimistic_critic:  { label: '🛡️ Pessimistic/Defensive',     bg: 'bg-red-900',    text: 'text-red-100',    align: 'items-start' },
  // Legacy role names for backward compatibility
  positive_critic:     { label: '✨ Optimistic Coding',         bg: 'bg-green-900',  text: 'text-green-100',  align: 'items-start' },
  negative_critic:     { label: '🛡️ Pessimistic/Defensive',     bg: 'bg-red-900',    text: 'text-red-100',    align: 'items-start' },
  critic:              { label: 'Critic',                       bg: 'bg-amber-900',  text: 'text-amber-100',  align: 'items-start' },
  thinking:            { label: '🤔 Thinking',                  bg: 'bg-purple-900', text: 'text-purple-100', align: 'items-start' },
  system:              { label: 'System',                       bg: 'bg-slate-600',  text: 'text-slate-300',  align: 'items-start' },
};

/**
 * Strip markdown code fences from text so the chat shows only natural language.
 */
function stripCodeBlocks(text) {
  // Remove fenced code blocks (```...```)
  let result = text.replace(/```[\s\S]*?```/g, '').trim();
  // Remove inline code (`...`)
  result = result.replace(/`[^`]+`/g, '').trim();
  // Collapse multiple blank lines into one
  result = result.replace(/\n{3,}/g, '\n\n');
  return result || '(see code viewer →)';
}

function ChatBubble({ role, content }) {
  const meta = ROLE_META[role] || ROLE_META.generator;
  const displayContent = stripCodeBlocks(content);

  return (
    <div className={`flex flex-col gap-1 ${meta.align}`}>
      <span className="text-xs text-slate-500 px-1">{meta.label}</span>
      <div className={`max-w-[90%] px-4 py-2 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap ${meta.bg} ${meta.text}`}>
        {displayContent}
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
