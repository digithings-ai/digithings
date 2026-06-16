'use client';

import { useMemo } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { computeDecisionScorecard } from '@/lib/decision-scorecard';
import type { TableRow } from '@/lib/database.types';
import { EmptyState, SectionCard, StatTile, fmtPct, signColorClass } from './shared';

const FIN_GREEN = '#3fb984';
const FIN_RED = '#e0654b';
const AXIS = '#71717a';
const BUCKET_LABEL: Record<string, string> = { low: 'Low (<2)', medium: 'Med (2–3)', high: 'High (≥4)' };

export default function DecisionScorecardTab({
  decisions,
}: {
  decisions: TableRow<'decision_log'>[];
}) {
  const scorecard = useMemo(() => computeDecisionScorecard(decisions), [decisions]);

  if (!scorecard) {
    return (
      <EmptyState
        title="No resolved decisions yet"
        message="The scorecard scores each analyst call once its holding window elapses and the resolver records realized alpha vs SPY. Decisions are still pending — check back after the next resolution run."
      />
    );
  }

  const chartData = scorecard.buckets.map((b) => ({
    bucket: BUCKET_LABEL[b.bucket] ?? b.bucket,
    meanAlphaPct: b.meanAlphaPct,
    n: b.n,
  }));

  return (
    <div className="flex flex-col gap-6">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <StatTile label="Resolved" value={scorecard.nResolved} sub={`${scorecard.nPending} pending`} />
        <StatTile
          label="Hit rate"
          value={`${scorecard.hitRatePct.toFixed(1)}%`}
          sub="positive alpha"
          color={scorecard.hitRatePct >= 50 ? 'text-fin-green' : 'text-fin-red'}
        />
        <StatTile
          label="Mean alpha"
          value={fmtPct(scorecard.meanAlphaPct)}
          sub="vs SPY, per call"
          color={signColorClass(scorecard.meanAlphaPct)}
        />
        <StatTile
          label="Median alpha"
          value={fmtPct(scorecard.medianAlphaPct)}
          color={signColorClass(scorecard.medianAlphaPct)}
        />
        <StatTile
          label="Calibration"
          value={scorecard.buckets.length < 2 ? 'n/a' : scorecard.calibrated ? 'Aligned' : 'Inverted'}
          sub="conviction → alpha"
          color={
            scorecard.buckets.length < 2
              ? 'text-text-secondary'
              : scorecard.calibrated
                ? 'text-fin-green'
                : 'text-fin-amber'
          }
        />
        <StatTile label="Buckets" value={scorecard.buckets.length} sub="with data" />
      </div>

      <SectionCard
        title="Conviction calibration"
        subtitle="Mean realized alpha (vs SPY) by conviction bucket. A well-calibrated book earns more alpha where it was more confident."
      >
        {chartData.length ? (
          <div className="h-[280px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
                <CartesianGrid stroke="rgba(255,255,255,0.05)" vertical={false} />
                <XAxis dataKey="bucket" tick={{ fill: AXIS, fontSize: 11 }} />
                <YAxis
                  tick={{ fill: AXIS, fontSize: 11 }}
                  tickFormatter={(v: number) => `${v}%`}
                />
                <Tooltip
                  cursor={{ fill: 'rgba(255,255,255,0.04)' }}
                  contentStyle={{
                    background: 'rgba(13,17,23,0.95)',
                    border: '1px solid rgba(255,255,255,0.1)',
                    borderRadius: 8,
                    fontSize: 12,
                  }}
                  formatter={(value: number, _name, item) => [
                    `${value}% (n=${item?.payload?.n})`,
                    'Mean alpha',
                  ]}
                />
                <Bar dataKey="meanAlphaPct" radius={[3, 3, 0, 0]} isAnimationActive={false}>
                  {chartData.map((d) => (
                    <Cell key={d.bucket} fill={d.meanAlphaPct >= 0 ? FIN_GREEN : FIN_RED} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <p className="text-xs text-text-muted">
            Resolved decisions exist but none carry a recorded conviction, so calibration buckets
            cannot be formed.
          </p>
        )}
      </SectionCard>

      <SectionCard title="By conviction bucket" subtitle="Per-bucket sample size, hit rate, and mean conviction.">
        <div className="overflow-x-auto">
          <table className="w-full text-sm tabular-nums">
            <thead>
              <tr className="text-left text-xs text-text-muted border-b border-border-subtle">
                <th className="py-2 pr-4 font-medium">Bucket</th>
                <th className="py-2 pr-4 font-medium text-right">N</th>
                <th className="py-2 pr-4 font-medium text-right">Mean alpha</th>
                <th className="py-2 pr-4 font-medium text-right">Hit rate</th>
                <th className="py-2 font-medium text-right">Mean conviction</th>
              </tr>
            </thead>
            <tbody>
              {scorecard.buckets.map((b) => (
                <tr key={b.bucket} className="border-b border-border-subtle/50">
                  <td className="py-2 pr-4 text-text-primary">{BUCKET_LABEL[b.bucket] ?? b.bucket}</td>
                  <td className="py-2 pr-4 text-right text-text-secondary">{b.n}</td>
                  <td className={`py-2 pr-4 text-right ${signColorClass(b.meanAlphaPct)}`}>
                    {fmtPct(b.meanAlphaPct)}
                  </td>
                  <td className="py-2 pr-4 text-right text-text-secondary">{b.hitRatePct.toFixed(1)}%</td>
                  <td className="py-2 text-right text-text-secondary">{b.meanConviction.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </SectionCard>
    </div>
  );
}
