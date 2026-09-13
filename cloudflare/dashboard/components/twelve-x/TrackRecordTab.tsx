'use client';

import { useMemo } from 'react';
import { History } from 'lucide-react';
import type {
  FxConsensusEvalRow,
  FxIdeaEvalRow,
  FxTradeIdeaRow,
} from '@/lib/twelve-x/types';
import {
  carriedIdeas,
  summarizeConsensusAccuracy,
  summarizeConsensusStability,
  summarizeIdeaOutcomes,
} from '@/lib/twelve-x/track-record';
import { biasLabel } from '@/lib/twelve-x/trade-history';
import CalibrationPanel from './CalibrationPanel';

/**
 * Track record tab: calibration (Wilson hit-rates for ideas + consensus),
 * corroboration (bank-vs-quant), and per-idea level-vs-fix rows. Wired to the
 * existing `summarize*` aggregations in `lib/twelve-x/track-record` — the tab
 * is what un-orphans that lib. `ideaEvalRaw` MUST be the un-netted eval rows
 * (`getIdeaEval({ netCarried: false })`) so the carried count stays honest.
 */
export default function TrackRecordTab({
  ideas,
  ideaEvalRaw,
  consensusEval,
}: {
  ideas: FxTradeIdeaRow[];
  ideaEvalRaw: FxIdeaEvalRow[];
  consensusEval: FxConsensusEvalRow[];
}) {
  const ideaSummary = useMemo(() => summarizeIdeaOutcomes(ideaEvalRaw), [ideaEvalRaw]);
  const stability = useMemo(() => summarizeConsensusStability(consensusEval), [consensusEval]);
  const accuracy = useMemo(() => summarizeConsensusAccuracy(consensusEval), [consensusEval]);
  const carried = useMemo(() => carriedIdeas(ideaEvalRaw), [ideaEvalRaw]);

  const titleByKey = useMemo(() => {
    const map = new Map<string, string>();
    for (const idea of ideas) map.set(`${idea.run_date}::${idea.rank}`, idea.title);
    return map;
  }, [ideas]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3 px-1">
        <History size={18} className="shrink-0 text-accent" aria-hidden />
        <h2 className="font-display text-2xl tracking-tight text-ink">Track record</h2>
      </div>
      <p className="max-w-2xl px-1 text-xs text-ink-mute">
        Whether past calls worked, with uncertainty shown instead of hidden. Idea
        outcomes use successor-clock closes; consensus reads use the 5-day window. Carried
        boards are counted raw (un-netted) so open exposure is never understated.
      </p>

      <CalibrationPanel
        ideaSummary={ideaSummary}
        consensusStability={stability}
        consensusAccuracy={accuracy}
      />

      <section className="oly-slab space-y-2 p-5" data-testid="track-record-carried">
        <p className="font-mono text-xs font-medium uppercase tracking-[0.08em] text-ink-soft">
          Open ideas · {carried.length}
        </p>
        {carried.length === 0 ? (
          <p className="text-sm text-ink-mute">No carried ideas — nothing currently live.</p>
        ) : (
          <ul className="divide-y divide-hair">
            {carried.map((row) => (
              <li
                key={`${row.run_date}-${row.rank}`}
                className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 py-1.5 text-xs"
              >
                <span className="font-mono text-ink-mute">{row.run_date}</span>
                <span className="font-semibold text-ink">{row.pair}</span>
                <span className="font-semibold uppercase text-ink-soft">
                  {biasLabel(row.direction)}
                </span>
                <span className="min-w-0 flex-1 truncate text-ink-mute">
                  {titleByKey.get(`${row.run_date}::${row.rank}`) ?? ''}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
