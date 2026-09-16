'use client';

import { useMemo } from 'react';
import { ArrowLeft } from 'lucide-react';

import { assembleTradeHistory, biasLabel } from '@/lib/twelve-x/trade-history';
import type { FxIdeaEvalRow, FxTradeIdeaRow } from '@/lib/twelve-x/types';
import { useTwelveX } from './context';

/**
 * The full live trade-idea book as cards — the Trades table summarizes the
 * same ideas, so this view is deliberately NOT a tab: it opens like the
 * all-briefs list (?view=ideas) from Today's "see more". Strictly live ideas;
 * old closures stay in the Trades table. Clicking a card opens the idea
 * sidebar with the argument and lifecycle.
 */
export default function IdeaCardsIndex({
  ideas,
  ideaEval,
  onBack,
}: {
  ideas: FxTradeIdeaRow[];
  ideaEval: FxIdeaEvalRow[];
  onBack: () => void;
}) {
  const { openIdea } = useTwelveX();
  const liveRows = useMemo(
    () => assembleTradeHistory(ideas, ideaEval).filter((r) => r.lifecycle === 'live'),
    [ideas, ideaEval],
  );

  return (
    <section className="flex flex-col gap-4">
      <header className="flex min-w-0 flex-wrap items-center gap-3">
        <button
          type="button"
          className="flex items-center gap-1 text-xs text-accent hover:underline"
          onClick={onBack}
        >
          <ArrowLeft size={14} /> Today
        </button>
        <h2 className="text-base font-semibold text-ink">Live trade ideas</h2>
        <span className="font-mono text-[10px] text-ink-mute">
          {liveRows.length} {liveRows.length === 1 ? 'idea' : 'ideas'}
        </span>
      </header>

      {liveRows.length === 0 ? (
        <div className="oly-slab p-10 text-center text-sm text-ink-mute">
          No live trade ideas right now — everything has closed. The Trades table keeps the full
          history.
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {liveRows.map((row) => (
            <button
              key={`${row.runDate}-${row.rank}`}
              type="button"
              className="oly-slab p-4 text-left transition-colors hover:border-accent/50"
              onClick={() => openIdea(row.runDate, row.rank)}
            >
              <div className="flex min-w-0 items-center gap-2 text-[11px] text-ink-mute">
                <span className="min-w-0 truncate font-semibold text-ink-soft">{row.pair}</span>
                <span className="shrink-0 uppercase">· {biasLabel(row.direction)}</span>
                <span className="ml-auto shrink-0 font-mono">Live</span>
              </div>
              <p className="mt-1 truncate text-sm font-medium text-ink">
                {row.title || `${row.pair} ${biasLabel(row.direction)}`}
              </p>
              <p className="mt-2 font-mono text-[11px] tabular-nums text-ink-soft">
                Entry {row.entryBand ?? '—'} · Stop {row.stop ?? '—'} · Target {row.target ?? '—'}
              </p>
              <p className="mt-1 font-mono text-[10px] text-ink-mute">
                {row.runDate} #{row.rank}
                {row.continuedFrom ? ` · cont. since ${row.continuedFrom}` : ''}
                {row.levelsUpdated ? ' · updated' : ''}
              </p>
            </button>
          ))}
        </div>
      )}
    </section>
  );
}
