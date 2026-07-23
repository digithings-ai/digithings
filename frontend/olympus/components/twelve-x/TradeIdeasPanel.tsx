'use client';

import { useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import type { FxTradeIdeaRow, FxConfluenceSnapshotRow } from '@/lib/twelve-x/types';
import { useTwelveX } from './context';
import { TwelveXSectionHeading } from './TwelveXSectionHeading';

function dirClass(direction: string): string {
  const d = direction.toLowerCase();
  if (d.includes('long') || d.includes('bull')) return 'text-accent';
  if (d.includes('short') || d.includes('bear')) return 'text-warn';
  return 'text-ink-mute';
}

/**
 * Human label for a citation object. Trade ideas are run artifacts — their
 * citations name contributing desks but do NOT resolve to loadable briefs, so
 * the panel expands detail in place instead of opening the brief slide-over.
 */
function citationLabel(c: unknown): string | null {
  if (!c || typeof c !== 'object') return null;
  const rec = c as Record<string, unknown>;
  for (const key of ['broker', 'broker_name', 'desk', 'source']) {
    if (typeof rec[key] === 'string' && (rec[key] as string).trim()) return rec[key] as string;
  }
  if (typeof rec.source_file === 'string' && rec.source_file.trim()) {
    const stem = rec.source_file.split('/').pop() ?? rec.source_file;
    return stem.replace(/\.(md|json|pdf)$/i, '').replace(/[-_]+/g, ' ');
  }
  return null;
}

function contributingDesks(citations: unknown[]): string[] {
  return [...new Set(citations.map(citationLabel).filter((v): v is string => !!v))];
}

function IdeaDetail({ idea }: { idea: FxTradeIdeaRow }) {
  const desks = contributingDesks(idea.citations);
  return (
    <div className="mt-2 space-y-2 border-t border-hair pt-2 text-left">
      {idea.thesis ? <p className="text-xs leading-relaxed text-ink-soft">{idea.thesis}</p> : null}
      {idea.catalyst ? (
        <p className="text-[11px] text-ink-mute">Catalyst: {idea.catalyst}</p>
      ) : null}
      {desks.length > 0 ? (
        <p className="text-[11px] text-ink-mute">
          Contributing desks: <span className="text-ink-soft">{desks.join(' · ')}</span>
        </p>
      ) : null}
    </div>
  );
}

export default function TradeIdeasPanel({
  ideas,
  confluence,
}: {
  ideas: FxTradeIdeaRow[];
  confluence: FxConfluenceSnapshotRow[];
}) {
  const { crossLink } = useTwelveX();
  const [expanded, setExpanded] = useState(false);
  const [openRank, setOpenRank] = useState<number | null>(null);
  const toggleIdea = (rank: number) => setOpenRank((v) => (v === rank ? null : rank));

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

  return (
    <section className="glass-card flex flex-col gap-3 p-5">
      <header className="flex items-baseline gap-2">
        <TwelveXSectionHeading>Today&rsquo;s trade ideas</TwelveXSectionHeading>
        <span className="font-mono text-[10px] text-ink-mute">· {ideas.length}</span>
        <button
          type="button"
          className="ml-auto text-[11px] text-accent hover:underline"
          onClick={() => crossLink({ kind: 'tab', tab: 'consensus' })}
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
        onClick={() => toggleIdea(top.rank)}
        aria-expanded={openRank === top.rank}
      >
        <div className="flex items-center gap-2">
          <span className="font-mono text-[11px] text-ink-mute">#1</span>
          <span className="font-semibold text-ink">{top.pair}</span>
          <span className={`text-xs font-semibold uppercase ${dirClass(top.direction)}`}>{top.direction}</span>
        </div>
        <p className="mt-1 text-sm text-ink">{top.title}</p>
        {openRank === top.rank ? (
          <IdeaDetail idea={top} />
        ) : (
          <>
            {top.thesis ? <p className="mt-1 line-clamp-2 text-xs text-ink-soft">{top.thesis}</p> : null}
            {top.catalyst ? <p className="mt-1 text-[11px] text-ink-mute">Catalyst: {top.catalyst}</p> : null}
          </>
        )}
      </button>

      {/* #2…N rows — expand in place; ideas are run artifacts with no brief */}
      {rest.map((idea) => (
        <button
          key={`${idea.run_date}-${idea.rank}`}
          type="button"
          className="rounded-md border border-hair px-3 py-2 text-left text-xs transition-colors hover:border-accent/50"
          onClick={() => toggleIdea(idea.rank)}
          aria-expanded={openRank === idea.rank}
        >
          <span className="flex items-center gap-2">
            <span className="font-mono text-[10px] text-ink-mute">#{idea.rank}</span>
            <span className="font-semibold text-ink">{idea.pair}</span>
            <span className={`font-semibold uppercase ${dirClass(idea.direction)}`}>{idea.direction}</span>
            <span className="ml-auto truncate text-ink-mute">{idea.title}</span>
          </span>
          {openRank === idea.rank ? <IdeaDetail idea={idea} /> : null}
        </button>
      ))}

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
