'use client';

import { ChevronDown, Terminal } from 'lucide-react';

const FLAGS: { flag: string; desc: string }[] = [
  { flag: '--baseline', desc: 'Full pipeline — every research phase regenerated from scratch' },
  { flag: '--delta', desc: 'Lightweight refresh — only changed segments re-run (~20–30% of baseline cost)' },
  { flag: '--monthly', desc: 'Month-end synthesis across the period’s baselines and deltas' },
];

export function OperatorControls() {
  return (
    <details className="glass-card group p-0">
      <summary className="flex cursor-pointer list-none items-center gap-2 p-4 text-sm text-ink-soft">
        <Terminal size={14} className="text-ink-mute" />
        <span className="font-medium text-ink">Operator controls</span>
        <span className="text-ink-mute">— for self-hosters running the pipeline</span>
        <ChevronDown size={14} className="ml-auto transition-transform group-open:rotate-180" aria-hidden />
      </summary>
      <div className="space-y-4 border-t border-hair p-4 text-sm">
        <p className="text-ink-mute">
          Runs are invoked from the command line. Model routing is automatic — chat phases use the
          configured reasoning model, web-search phases route to a grounding model.
        </p>
        <ul className="space-y-1.5">
          {FLAGS.map((f) => (
            <li key={f.flag} className="flex flex-col gap-0.5 sm:flex-row sm:gap-3">
              <code className="shrink-0 font-mono text-xs text-[var(--accent)]">{f.flag}</code>
              <span className="text-ink-mute">{f.desc}</span>
            </li>
          ))}
        </ul>
      </div>
    </details>
  );
}
