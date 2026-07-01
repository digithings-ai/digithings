'use client';

import { useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import type { FxTradeIdeaRow, FxConfluenceSnapshotRow } from '@/lib/twelve-x/types';
import { useTwelveX } from './context';

function dirClass(direction: string): string {
  const d = direction.toLowerCase();
  if (d.includes('long') || d.includes('bull')) return 'text-fin-green';
  if (d.includes('short') || d.includes('bear')) return 'text-fin-red';
  return 'text-text-muted';
}

function firstSource(citations: unknown[]): string | null {
  for (const c of citations) {
    if (c && typeof c === 'object' && typeof (c as Record<string, unknown>).source_file === 'string') {
      return (c as Record<string, unknown>).source_file as string;
    }
  }
  return null;
}

export default function TradeIdeasPanel({
  ideas,
  confluence,
}: {
  ideas: FxTradeIdeaRow[];
  confluence: FxConfluenceSnapshotRow[];
}) {
  const { crossLink, openBrief } = useTwelveX();
  const [expanded, setExpanded] = useState(false);

  if (ideas.length === 0) {
    return (
      <section className="glass-card p-5">
        <header className="mb-2 flex items-baseline gap-2">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-text-secondary">Today&rsquo;s trade ideas</h2>
        </header>
        <p className="text-sm text-text-muted">No curated trade idea for today yet.</p>
      </section>
    );
  }

  const [top, ...rest] = ideas;
  const topSource = firstSource(top.citations);

  return (
    <section className="glass-card flex flex-col gap-3 p-5">
      <header className="flex items-baseline gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-text-secondary">Today&rsquo;s trade ideas</h2>
        <span className="font-mono text-[10px] text-text-muted">· {ideas.length}</span>
        <button
          type="button"
          className="ml-auto text-[11px] text-fin-blue hover:underline"
          onClick={() => crossLink({ kind: 'tab', tab: 'intelligence' })}
        >
          see more →
        </button>
      </header>

      {/* Focal #1 */}
      <button
        type="button"
        className="rounded-lg border border-fin-green/30 bg-fin-green/[0.06] p-4 text-left transition-colors hover:border-fin-blue/50"
        onClick={() => topSource && openBrief(topSource, top.run_date)}
      >
        <div className="flex items-center gap-2">
          <span className="font-mono text-[11px] text-text-muted">#1</span>
          <span className="font-semibold text-text-primary">{top.pair}</span>
          <span className={`text-xs font-semibold uppercase ${dirClass(top.direction)}`}>{top.direction}</span>
        </div>
        <p className="mt-1 text-sm text-text-primary">{top.title}</p>
        {top.thesis ? <p className="mt-1 line-clamp-2 text-xs text-text-secondary">{top.thesis}</p> : null}
        {top.catalyst ? <p className="mt-1 text-[11px] text-text-muted">Catalyst: {top.catalyst}</p> : null}
      </button>

      {/* #2…N rows */}
      {rest.map((idea) => {
        const src = firstSource(idea.citations);
        return (
          <button
            key={`${idea.run_date}-${idea.rank}`}
            type="button"
            className="flex items-center gap-2 rounded-md border border-border-subtle px-3 py-2 text-left text-xs transition-colors hover:border-fin-blue/50"
            onClick={() => src && openBrief(src, idea.run_date)}
          >
            <span className="font-mono text-[10px] text-text-muted">#{idea.rank}</span>
            <span className="font-semibold text-text-primary">{idea.pair}</span>
            <span className={`font-semibold uppercase ${dirClass(idea.direction)}`}>{idea.direction}</span>
            <span className="ml-auto truncate text-text-muted">{idea.title}</span>
          </button>
        );
      })}

      {/* Expand → confluence reads */}
      {confluence.length > 0 ? (
        <div>
          <button
            type="button"
            className="flex items-center gap-1 text-[11px] text-text-secondary hover:text-fin-blue"
            onClick={() => setExpanded((v) => !v)}
            aria-expanded={expanded}
          >
            {expanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
            {expanded ? 'Hide' : 'Expand'} confluence reads ({confluence.length})
          </button>
          {expanded ? (
            <ul className="mt-2 grid gap-1">
              {confluence.map((c) => (
                <li key={`${c.run_date}-${c.rank}`} className="flex items-center gap-2 rounded-md border border-border-subtle px-3 py-1.5 text-xs">
                  <span className="font-mono text-[10px] text-text-muted">#{c.rank}</span>
                  <span className="font-semibold text-text-primary">{c.currency}</span>
                  <span className={`uppercase ${dirClass(c.direction)}`}>{c.direction}</span>
                  <button
                    type="button"
                    className="ml-auto text-fin-blue hover:underline"
                    onClick={() => crossLink({ kind: 'currency', currency: c.currency })}
                  >
                    trend →
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
