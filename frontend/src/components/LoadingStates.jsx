/**
 * LoadingStates.jsx – Dynamic status indicator for the pipeline steps.
 *
 * Shows the current pipeline phase:
 *   "Generator is drafting…"  →  "Critics are reviewing…"  →  "Applying fixes…"
 */
export default function LoadingStates({ phase }) {
  if (!phase) return null;

  const steps = [
    { id: 'generating', label: 'Generator is drafting…'  },
    { id: 'reviewing',  label: 'Critics are reviewing…'  },
    { id: 'applying',   label: 'Applying fixes…'         },
  ];

  const current = steps.findIndex(s => s.id === phase);

  return (
    <div className="flex flex-col gap-2 p-4 bg-slate-800 rounded-lg border border-slate-700">
      {steps.map((step, idx) => {
        const isDone    = idx < current;
        const isActive  = idx === current;
        const isPending = idx > current;

        return (
          <div key={step.id} className="flex items-center gap-3">
            {/* Spinner / tick / circle */}
            <span className="w-5 h-5 flex items-center justify-center flex-shrink-0">
              {isDone && (
                <svg className="w-4 h-4 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
              )}
              {isActive && (
                <span className="inline-block w-4 h-4 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
              )}
              {isPending && (
                <span className="inline-block w-3 h-3 rounded-full bg-slate-600" />
              )}
            </span>

            <span
              className={
                isDone    ? 'text-sm text-green-400 line-through opacity-60' :
                isActive  ? 'text-sm text-blue-300 font-semibold animate-pulse' :
                            'text-sm text-slate-500'
              }
            >
              {step.label}
            </span>
          </div>
        );
      })}
    </div>
  );
}
