'use client';

import { useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import type { FxTradeIdeaRow, FxConfluenceSnapshotRow } from '@/lib/twelve-x/types';
import { useTwelveX } from './context';
import { TwelveXSectionHeading } from './TwelveXSectionHeading';

function dirClass(direction: string): string {
  const d = direction.toLowerCase();
  if (d.includes('long') || d.includes('bull')) return 'text-up';
  if (d.includes('short') || d.includes('bear')) return 'text-down';
  return 'text-ink-mute';
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
          <TwelveXSectionHeading>Today&rsquo;s trade ideas</TwelveXSectionHeading>
        </header>
        <p className="text-sm text-ink-mute">No curated trade idea for today yet.</p>
      </section>
    );
  }

  const [top, ...rest] = ideas;
  const topSource = firstSource(top.citations);

  return (
    <section className="glass-card flex flex-col gap-3 p-5">
      <header className="flex items-baseline gap-2">
        <TwelveXSectionHeading>Today&rsquo;s trade ideas</TwelveXSectionHeading>
        <span className="font-mono text-[10px] text-ink-mute">· {ideas.length}</span>
        <button
          type="button"
          className="ml-auto text-[11px] text-accent hover:underline"
          onClick={() => crossLink({ kind: 'tab', tab: 'intelligence' })}
        >
          see more →
        </button>
      </header>

      {/* Focal #1 — accent chrome marks it as the top-ranked idea, NOT a P&L
          direction. --up/--down are reserved for P&L sign (F5), so a SHORT #1
          must not read as green. Direction lives in its own colored label. */}
      <button
        type="button"
        className="rounded-lg border border-accent/30 bg-accent/[0.06] p-4 text-left transition-colors hover:border-accent/50"
        onClick={() => topSource && openBrief(topSource, top.run_date)}
      >
        <div className="flex items-center gap-2">
          <span className="font-mono text-[11px] text-ink-mute">#1</span>
          <span className="font-semibold text-ink">{top.pair}</span>
          <span className={`text-xs font-semibold uppercase ${dirClass(top.direction)}`}>{top.direction}</span>
        </div>
        <p className="mt-1 text-sm text-ink">{top.title}</p>
        {top.thesis ? <p className="mt-1 line-clamp-2 text-xs text-ink-soft">{top.thesis}</p> : null}
        {top.catalyst ? <p className="mt-1 text-[11px] text-ink-mute">Catalyst: {top.catalyst}</p> : null}
      </button>

      {/* #2…N rows */}
      {rest.map((idea) => {
        const src = firstSource(idea.citations);
        return (
          <button
            key={`${idea.run_date}-${idea.rank}`}
            type="button"
            className="flex items-center gap-2 rounded-md border border-hair px-3 py-2 text-left text-xs transition-colors hover:border-accent/50"
            onClick={() => src && openBrief(src, idea.run_date)}
          >
            <span className="font-mono text-[10px] text-ink-mute">#{idea.rank}</span>
            <span className="font-semibold text-ink">{idea.pair}</span>
            <span className={`font-semibold uppercase ${dirClass(idea.direction)}`}>{idea.direction}</span>
            <span className="ml-auto truncate text-ink-mute">{idea.title}</span>
          </button>
        );
      })}

      {/* Expand → confluence reads */}
      {confluence.length > 0 ? (
        <div>
          <button
            type="button"
            className="flex items-center gap-1 text-[11px] text-ink-soft hover:text-accent"
            onClick={() => setExpanded((v) => !v)}
            aria-expanded={expanded}
          >
            {expanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
            {expanded ? 'Hide' : 'Expand'} confluence reads ({confluence.length})
          </button>
          {expanded ? (
            <ul className="mt-2 grid gap-1">
              {confluence.map((c) => (
                <li key={`${c.run_date}-${c.rank}`} className="flex items-center gap-2 rounded-md border border-hair px-3 py-1.5 text-xs">
                  <span className="font-mono text-[10px] text-ink-mute">#{c.rank}</span>
                  <span className="font-semibold text-ink">{c.currency}</span>
                  <span className={`uppercase ${dirClass(c.direction)}`}>{c.direction}</span>
                  <button
                    type="button"
                    className="ml-auto text-accent hover:underline"
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
