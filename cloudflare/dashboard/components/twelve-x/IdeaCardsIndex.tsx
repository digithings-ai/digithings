'use client';

import { useMemo } from 'react';
import { Button, Card } from '@digithings/web/ui';
import { ArrowLeft } from 'lucide-react';

import { annotateLevelUpdates, assembleTradeHistory, biasLabel } from '@/lib/twelve-x/trade-history';
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
    () =>
      annotateLevelUpdates(assembleTradeHistory(ideas, ideaEval)).filter(
        (r) => r.lifecycle === 'live',
      ),
    [ideas, ideaEval],
  );

  return (
    <section className="flex flex-col gap-4">
      <header className="flex min-w-0 flex-wrap items-center gap-3">
        <Button
          type="button"
          variant="link"
          size="xs"
          className="h-auto justify-start gap-1 p-0 text-xs text-accent"
          onClick={onBack}
        >
          <ArrowLeft size={14} /> Today
        </Button>
        <h2 className="text-base font-semibold text-ink">Live trade ideas</h2>
        <span className="font-mono text-[10px] text-ink-mute">
          {liveRows.length} {liveRows.length === 1 ? 'idea' : 'ideas'}
        </span>
      </header>

      {liveRows.length === 0 ? (
        <Card data-reveal className="gap-0 p-10 text-center text-sm text-ink-mute">
          No live trade ideas right now — everything has closed. The Trades table keeps the full
          history.
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {liveRows.map((row) => (
            <Card
              key={`${row.runDate}-${row.rank}`}
              data-reveal
              className="gap-0 p-0 transition-colors hover:ring-accent/50"
            >
              <Button
                type="button"
                variant="ghost"
                className="block h-auto w-full justify-start whitespace-normal rounded-none p-4 text-left text-xs font-normal hover:bg-transparent"
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
              </Button>
            </Card>
          ))}
        </div>
      )}
    </section>
  );
}
