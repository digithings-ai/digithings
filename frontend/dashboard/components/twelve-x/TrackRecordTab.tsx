'use client';

import { useMemo } from 'react';
import { ClipboardList } from 'lucide-react';
import type { FxConsensusEvalRow, FxIdeaEvalRow } from '@/lib/twelve-x/types';
import {
  openIdeas,
  summarizeConsensusAccuracy,
  summarizeConsensusStability,
  summarizeIdeaOutcomes,
} from '@/lib/twelve-x/track-record';
import { formatWilsonPct } from '@/lib/twelve-x/wilson';

function RateCard({
  title,
  subtitle,
  primary,
  longLabel,
  shortLabel,
}: {
  title: string;
  subtitle?: string;
  primary: string;
  longLabel?: string;
  shortLabel?: string;
}) {
  return (
    <div className="space-y-1 border border-hair bg-surface/40 px-3 py-2.5">
      <p className="text-[11px] font-medium uppercase tracking-wider text-ink-mute">{title}</p>
      {subtitle ? <p className="text-[10px] text-ink-mute">{subtitle}</p> : null}
      <p className="font-mono text-sm tabular-nums text-ink">{primary}</p>
      {longLabel || shortLabel ? (
        <p className="text-[10px] text-ink-mute">
          {longLabel ? <span>Long {longLabel}</span> : null}
          {longLabel && shortLabel ? <span> · </span> : null}
          {shortLabel ? <span>Short {shortLabel}</span> : null}
        </p>
      ) : null}
    </div>
  );
}

export default function TrackRecordTab({
  ideaEval,
  consensusEval,
}: {
  ideaEval: FxIdeaEvalRow[];
  consensusEval: FxConsensusEvalRow[];
}) {
  const ideaSummary = useMemo(() => summarizeIdeaOutcomes(ideaEval), [ideaEval]);
  const open = useMemo(() => openIdeas(ideaEval), [ideaEval]);
  const stability = useMemo(() => summarizeConsensusStability(consensusEval), [consensusEval]);
  const accuracy = useMemo(() => summarizeConsensusAccuracy(consensusEval), [consensusEval]);

  const weightedStab = stability.find((s) => s.weighted);
  const unweightedStab = stability.find((s) => !s.weighted);

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-center gap-3 px-1">
        <ClipboardList size={18} className="shrink-0 text-accent" aria-hidden />
        <h2 className="font-display text-2xl tracking-tight text-ink">Track record</h2>
      </div>
      <p className="max-w-2xl text-xs text-ink-mute">
        Research call scorecard — each idea holds until the next board that posts the
        same pair (successor clock). Directional outcomes use daily closes only; stop /
        target levels are experimental and not scored.
      </p>

      <section className="space-y-3">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-ink-mute">
          Trade ideas
        </h3>
        <div className="grid gap-3 sm:grid-cols-2">
          {ideaEval.length > 0 ? (
            <RateCard
              title="Resolved directional win rate"
              subtitle="Among successor-exited ideas; win = signed hold return > 0 (zero counts as loss)"
              primary={formatWilsonPct(ideaSummary.interval)}
              longLabel={formatWilsonPct(ideaSummary.longInterval)}
              shortLabel={formatWilsonPct(ideaSummary.shortInterval)}
            />
          ) : null}
          {ideaEval.length > 0 ? (
            <RateCard
              title="Outcome split"
              subtitle={`Wins ${ideaSummary.winCount} · Losses ${ideaSummary.lossCount} · significant moves ${ideaSummary.significantCount}`}
              primary={`Resolved ${ideaSummary.resolvedCount} · Open ${ideaSummary.openCount} · Missing ${ideaSummary.missingCount}`}
            />
          ) : null}
        </div>
        {ideaEval.length > 0 ? (
          <p className="text-[11px] text-ink-mute">
            Significant move means |hold return| ≥ 0.5 × entry 20d σ (optional overlay on
            the same hold). Missing rates: {ideaSummary.missingCount}.
          </p>
        ) : (
          <p className="text-sm text-ink-mute">No idea eval rows yet.</p>
        )}

        <div className="space-y-2">
          <h4 className="text-[11px] font-medium text-ink-soft">Open ideas</h4>
          {open.length === 0 ? (
            <p className="text-[11px] text-ink-mute">No live ideas.</p>
          ) : (
            <ul className="divide-y divide-hair border border-hair">
              {open.map((row) => (
                <li
                  key={`${row.run_date}-${row.rank}`}
                  className="flex flex-wrap items-baseline justify-between gap-2 px-3 py-2 text-xs"
                >
                  <span className="text-ink">
                    <span className="font-mono text-ink-mute">{row.run_date}</span>
                    {' · '}
                    {row.pair} {row.direction}
                  </span>
                  <span className="font-mono text-[10px] text-ink-mute">open</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>

      <section className="space-y-3">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-ink-mute">
          Consensus
        </h3>
        <div className="grid gap-3 sm:grid-cols-2">
          {weightedStab ? (
            <RateCard
              title="Stability (weighted medium)"
              subtitle={
                weightedStab.medianAbsDelta == null
                  ? 'No jumps yet'
                  : `Median |Δscore| ${weightedStab.medianAbsDelta.toFixed(2)} · n=${weightedStab.nJumps}`
              }
              primary={`Sign flip ${formatWilsonPct(weightedStab.signFlipPct)}`}
              longLabel={`|Δ|≥1 ${formatWilsonPct(weightedStab.largeJumpPct)}`}
            />
          ) : null}
          {unweightedStab ? (
            <RateCard
              title="Stability (unweighted)"
              subtitle={
                unweightedStab.medianAbsDelta == null
                  ? 'No jumps yet'
                  : `Median |Δscore| ${unweightedStab.medianAbsDelta.toFixed(2)} · n=${unweightedStab.nJumps}`
              }
              primary={`Sign flip ${formatWilsonPct(unweightedStab.signFlipPct)}`}
              longLabel={`|Δ|≥1 ${formatWilsonPct(unweightedStab.largeJumpPct)}`}
            />
          ) : null}
          <RateCard
            title="5d currency accuracy"
            subtitle="Medium score vs USD-cross move — weaker than pair ideas"
            primary={formatWilsonPct(accuracy.interval)}
            longLabel={`Significant ${formatWilsonPct(accuracy.significantInterval)}`}
            shortLabel={`Open ${accuracy.openCount} · Missing ${accuracy.missingCount}`}
          />
        </div>
      </section>
    </div>
  );
}
