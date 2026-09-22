'use client';

import { useMemo } from 'react';
import { Card } from '@digithings/ui/ui';
import { History } from 'lucide-react';
import type {
  FxConsensusDivergence,
  FxConsensusEvalRow,
  FxConsensusSnapshotRow,
  FxIdeaEvalRow,
  FxTradeIdeaRow,
} from '@/lib/twelve-x/types';
import {
  carriedIdeas,
  summarizeConsensusAccuracy,
  summarizeConsensusStability,
  summarizeIdeaOutcomes,
} from '@/lib/twelve-x/track-record';
import { summarizeDivergenceAccuracy } from '@/lib/twelve-x/divergence-accuracy';
import { deriveConsensusRows } from '@/lib/twelve-x/consensus-view';
import { biasLabel } from '@/lib/twelve-x/trade-history';
import CalibrationPanel from './CalibrationPanel';
import BankVsQuantPanel from './BankVsQuantPanel';
import LevelFixSection from './LevelFixSection';
import WilsonStat from './WilsonStat';

/** Latest archive ideas joined to their eval rows (newest first, capped). */
const RECENT_IDEA_ROWS = 8;

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
  divergenceByCurrency = {},
  series = [],
}: {
  ideas: FxTradeIdeaRow[];
  ideaEvalRaw: FxIdeaEvalRow[];
  consensusEval: FxConsensusEvalRow[];
  divergenceByCurrency?: Record<string, FxConsensusDivergence>;
  series?: FxConsensusSnapshotRow[];
}) {
  const ideaSummary = useMemo(() => summarizeIdeaOutcomes(ideaEvalRaw), [ideaEvalRaw]);
  const stability = useMemo(() => summarizeConsensusStability(consensusEval), [consensusEval]);
  const accuracy = useMemo(() => summarizeConsensusAccuracy(consensusEval), [consensusEval]);
  const carried = useMemo(() => carriedIdeas(ideaEvalRaw), [ideaEvalRaw]);
  const consensusRows = useMemo(() => deriveConsensusRows(series), [series]);
  const divAccuracy = useMemo(
    () => summarizeDivergenceAccuracy(divergenceByCurrency, consensusEval),
    [divergenceByCurrency, consensusEval],
  );

  const titleByKey = useMemo(() => {
    const map = new Map<string, string>();
    for (const idea of ideas) map.set(`${idea.run_date}::${idea.rank}`, idea.title);
    return map;
  }, [ideas]);

  const recentRows = useMemo(() => {
    const evalByKey = new Map(ideaEvalRaw.map((r) => [`${r.run_date}::${r.rank}`, r]));
    return ideas
      .filter((idea) => evalByKey.has(`${idea.run_date}::${idea.rank}`))
      .sort((a, b) => b.run_date.localeCompare(a.run_date) || a.rank - b.rank)
      .slice(0, RECENT_IDEA_ROWS)
      .map((idea) => ({ idea, evalRow: evalByKey.get(`${idea.run_date}::${idea.rank}`)! }));
  }, [ideas, ideaEvalRaw]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3 px-1">
        <History size={18} className="shrink-0 text-accent" aria-hidden />
        <h2 className="font-display text-xl tracking-tight text-ink">Track record</h2>
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

      <BankVsQuantPanel divergenceByCurrency={divergenceByCurrency} consensusRows={consensusRows} />

      <Card data-reveal className="gap-0 space-y-2 p-5" data-testid="track-record-divergence-accuracy">
        <p className="font-mono text-xs font-medium uppercase tracking-[0.08em] text-ink-soft">
          Divergent-call accuracy
        </p>
        <p className="max-w-2xl text-xs text-ink-mute">
          5-day hit-rate split by whether the currency is currently divergent —
          descriptive, not causal.
        </p>
        <div className="flex flex-wrap gap-x-6 gap-y-2">
          <WilsonStat label="Divergent now" interval={divAccuracy.divergent} />
          <WilsonStat label="Aligned now" interval={divAccuracy.aligned} />
        </div>
      </Card>

      <Card data-reveal className="gap-0 space-y-2 p-5" data-testid="track-record-carried">
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
      </Card>

      <section className="space-y-3" data-testid="track-record-recent">
        <p className="px-1 font-mono text-xs font-medium uppercase tracking-[0.08em] text-ink-soft">
          Recent ideas · levels vs fix
        </p>
        {recentRows.length === 0 ? (
          <p className="px-1 text-sm text-ink-mute">No scored ideas with published levels yet.</p>
        ) : (
          recentRows.map(({ idea, evalRow }) => (
            <Card
              key={`${idea.run_date}-${idea.rank}`}
              data-reveal
              className="gap-0 space-y-2 p-5"
            >
              <div className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 text-xs">
                <span className="font-mono text-ink-mute">{idea.run_date}</span>
                <span className="font-semibold text-ink">{idea.pair}</span>
                <span className="font-semibold uppercase text-ink-soft">
                  {biasLabel(idea.direction)}
                </span>
                <span className="font-mono text-[10px] text-ink-mute">{evalRow.status}</span>
                <span className="min-w-0 flex-1 truncate text-ink-mute">{idea.title}</span>
              </div>
              <LevelFixSection idea={idea} evalRow={evalRow} />
            </Card>
          ))
        )}
      </section>
    </div>
  );
}
