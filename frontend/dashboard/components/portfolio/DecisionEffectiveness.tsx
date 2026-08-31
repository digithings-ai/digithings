'use client';

import { useMemo } from 'react';
import {
  computeDecisionScorecard,
  scoredDecisionEpisodes,
  type DecisionRecord,
  type ScoredDecisionEpisode,
} from '@/lib/decision-scorecard';
import { StatTile, fmtPct, signColorClass } from '@/components/observability/shared';
import DecisionEdgeChart, { type DecisionEdgePoint } from './DecisionEdgeChart';

function mean(values: number[]): number {
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : 0;
}

export function buildDecisionEdgeTrend(
  episodes: ScoredDecisionEpisode[]
): DecisionEdgePoint[] {
  const sorted = [...episodes].sort((a, b) =>
    (a.decision.run_date ?? '').localeCompare(b.decision.run_date ?? '')
  );
  const byDate = new Map<string, DecisionEdgePoint>();
  let cumulativeAlpha = 0;
  let datedDecisionCount = 0;
  sorted.forEach((episode) => {
    const date = episode.decision.run_date;
    if (!date) return;
    cumulativeAlpha += episode.directionalAlpha;
    datedDecisionCount += 1;
    byDate.set(date, {
      date,
      value: (cumulativeAlpha / datedDecisionCount) * 100,
    });
  });
  return [...byDate.values()];
}

function stanceStats(episodes: ScoredDecisionEpisode[]) {
  const groups = new Map<string, number[]>();
  episodes.forEach((episode) => {
    const stance = episode.decision.stance?.trim().toLowerCase() ?? 'unknown';
    groups.set(stance, [...(groups.get(stance) ?? []), episode.directionalAlpha]);
  });
  return [...groups.entries()]
    .map(([stance, alphas]) => ({
      stance,
      n: alphas.length,
      meanAlphaPct: mean(alphas) * 100,
      hitRatePct: (alphas.filter((alpha) => alpha > 0).length / alphas.length) * 100,
    }))
    .sort((a, b) => b.n - a.n);
}

export default function DecisionEffectiveness({
  decisions,
}: {
  decisions: DecisionRecord[];
}) {
  const scorecard = useMemo(() => computeDecisionScorecard(decisions), [decisions]);
  const episodes = useMemo(() => scoredDecisionEpisodes(decisions), [decisions]);
  const trend = useMemo(() => buildDecisionEdgeTrend(episodes), [episodes]);
  const stances = useMemo(() => stanceStats(episodes), [episodes]);
  const reviewQueue = useMemo(
    () => [...episodes].sort((a, b) => a.directionalAlpha - b.directionalAlpha).slice(0, 5),
    [episodes]
  );

  if (!scorecard) {
    return (
      <div className="border-y border-hair py-8 text-sm text-ink-mute">
        No resolved directional decisions are available yet.
      </div>
    );
  }

  return (
    <div className="space-y-7">
      <div className="grid grid-cols-2 border-l border-t border-hair lg:grid-cols-4">
        <StatTile
          label="Mean decision edge"
          value={fmtPct(scorecard.meanAlphaPct)}
          sub="vs recorded benchmark"
          color={signColorClass(scorecard.meanAlphaPct)}
          flat
        />
        <StatTile
          label="Directional hit rate"
          value={`${scorecard.hitRatePct.toFixed(1)}%`}
          sub="correct directional calls"
          color={scorecard.hitRatePct >= 50 ? 'text-up' : 'text-down'}
          flat
        />
        <StatTile
          label="Edge consistency"
          value={scorecard.informationRatio.toFixed(2)}
          sub="mean edge / variability"
          color={signColorClass(scorecard.informationRatio)}
          flat
        />
        <StatTile
          label="Decisions scored"
          value={scorecard.nResolved}
          sub={`${scorecard.nPending} awaiting outcomes`}
          flat
        />
      </div>

      <div className="grid gap-7 xl:grid-cols-[minmax(0,1.65fr)_minmax(19rem,0.85fr)]">
        <section className="border-y border-hair py-5" aria-labelledby="decision-edge-heading">
          <div className="space-y-1">
            <p className="font-mono text-[11px] uppercase text-ink-mute">Trend</p>
            <h2 id="decision-edge-heading" className="text-sm font-semibold text-ink">
              Decision edge over time
            </h2>
          </div>
          <p className="mt-2 font-mono text-[11px] text-ink-mute">
            Cumulative mean decision edge · all scored decisions in period
          </p>
          {trend.length >= 2 ? (
            <div className="mt-4">
              <DecisionEdgeChart points={trend} />
            </div>
          ) : (
            <div className="mt-4 flex h-[260px] items-center justify-center border border-dashed border-hair text-xs text-ink-mute">
              Two dated decisions are required to draw the trend.
            </div>
          )}
        </section>

        <section className="border-y border-hair py-5" aria-labelledby="review-queue-heading">
          <div className="flex items-end justify-between gap-4">
            <div className="space-y-1">
              <p className="font-mono text-[11px] uppercase text-ink-mute">Investigate</p>
              <h2 id="review-queue-heading" className="text-sm font-semibold text-ink">
                Review queue
              </h2>
            </div>
            <span className="font-mono text-[11px] text-ink-mute">lowest decision edge</span>
          </div>
          <ol className="mt-4 divide-y divide-hair">
            {reviewQueue.map((episode, index) => (
              <li key={episode.decision.id ?? `${episode.decision.ticker}-${index}`} className="grid grid-cols-[2rem_minmax(0,1fr)_auto] items-center gap-3 py-3">
                <span className="font-mono text-[11px] text-ink-mute">{String(index + 1).padStart(2, '0')}</span>
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-ink">
                    {episode.decision.ticker ?? '—'}
                    <span className="ml-2 font-normal capitalize text-ink-mute">
                      {episode.decision.stance ?? '—'}
                    </span>
                  </p>
                  <p className="font-mono text-[11px] text-ink-mute">
                    {episode.decision.run_date ?? '—'} · conviction {episode.decision.conviction ?? '—'}
                  </p>
                </div>
                <strong className={`font-mono text-xs ${signColorClass(episode.directionalAlpha)}`}>
                  {fmtPct(episode.directionalAlpha * 100)}
                </strong>
              </li>
            ))}
          </ol>
        </section>
      </div>

      <div className="grid gap-7 lg:grid-cols-2">
        <section className="border-y border-hair py-5" aria-labelledby="stance-diagnostics-heading">
          <div className="space-y-1">
            <p className="font-mono text-[11px] uppercase text-ink-mute">Segmentation</p>
            <h2 id="stance-diagnostics-heading" className="text-sm font-semibold text-ink">
              Edge by stance
            </h2>
          </div>
          <div className="mt-4 overflow-x-auto">
            <table className="w-full text-sm tabular-nums">
              <thead>
                <tr className="border-b border-hair text-left font-mono text-[11px] uppercase text-ink-mute">
                  <th className="py-2 pr-3 font-normal">Stance</th>
                  <th className="py-2 pr-3 text-right font-normal">N</th>
                  <th className="py-2 pr-3 text-right font-normal">Mean edge</th>
                  <th className="py-2 text-right font-normal">Hit rate</th>
                </tr>
              </thead>
              <tbody>
                {stances.map((item) => (
                  <tr key={item.stance} className="border-b border-hair/50">
                    <td className="py-2.5 pr-3 capitalize text-ink">{item.stance}</td>
                    <td className="py-2.5 pr-3 text-right text-ink-soft">{item.n}</td>
                    <td className={`py-2.5 pr-3 text-right ${signColorClass(item.meanAlphaPct)}`}>
                      {fmtPct(item.meanAlphaPct)}
                    </td>
                    <td className="py-2.5 text-right text-ink-soft">{item.hitRatePct.toFixed(1)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="border-y border-hair py-5" aria-labelledby="conviction-diagnostics-heading">
          <div className="flex items-end justify-between gap-4">
            <div className="space-y-1">
              <p className="font-mono text-[11px] uppercase text-ink-mute">Calibration</p>
              <h2 id="conviction-diagnostics-heading" className="text-sm font-semibold text-ink">
                Edge by conviction
              </h2>
            </div>
            <span className={`font-mono text-[11px] uppercase ${
              scorecard.calibrationEvidence === 'aligned'
                ? 'text-up'
                : scorecard.calibrationEvidence === 'inverted'
                  ? 'text-warn'
                  : 'text-ink-mute'
            }`}>
              {scorecard.calibrationEvidence === 'insufficient'
                ? 'Insufficient evidence'
                : scorecard.calibrationEvidence}
            </span>
          </div>
          <div className="mt-4 grid grid-cols-3 border-l border-t border-hair">
            {(['low', 'medium', 'high'] as const).map((bucket) => {
              const row = scorecard.buckets.find((item) => item.bucket === bucket);
              return (
                <div key={bucket} className="border-b border-r border-hair p-3">
                  <p className="font-mono text-[10px] uppercase text-ink-mute">{bucket}</p>
                  <strong className={`mt-2 block text-lg ${signColorClass(row?.meanAlphaPct)}`}>
                    {row ? fmtPct(row.meanAlphaPct) : '—'}
                  </strong>
                  <span className="text-[11px] text-ink-mute">n={row?.n ?? 0}</span>
                </div>
              );
            })}
          </div>
          <p className="mt-3 text-xs text-ink-mute">
            Verdict requires at least two conviction buckets with 10 or more independent decisions.
          </p>
        </section>
      </div>
    </div>
  );
}