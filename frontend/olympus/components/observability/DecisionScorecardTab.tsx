'use client';

import { useMemo, useState } from 'react';
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
// Buckets use |conviction| thresholds (magnitude), matching decision-scorecard.ts and backtest.py:
//   low    |conv| < 2
//   medium |conv| ≥ 2 and < 4
//   high   |conv| ≥ 4
// The conviction domain is [−5, +5], so "high" is ±4–5, not "just 5".
const BUCKET_LABEL: Record<string, string> = {
  low: 'Low (|conv|<2)',
  medium: 'Med (|conv| 2–3)',
  high: 'High (|conv|≥4)',
};

/** Per-decision drill-down row — expanded inline to keep the table scannable. */
function ReasoningExpander({ thesis, reflection }: { thesis: string | null; reflection: string | null }) {
  const [open, setOpen] = useState(false);
  if (!thesis && !reflection) {
    return <span className="text-ink-mute/50 text-xs italic">none recorded</span>;
  }
  return (
    <div className="flex flex-col gap-1">
      <button
        onClick={() => setOpen((v) => !v)}
        className="text-xs text-ink-soft underline underline-offset-2 decoration-dotted hover:text-ink text-left"
        aria-expanded={open}
      >
        {open ? 'hide' : 'show reasoning'}
      </button>
      {open && (
        <div className="flex flex-col gap-2 text-xs mt-1 max-w-prose">
          {thesis && (
            <div>
              <span className="text-ink-mute font-medium">Thesis: </span>
              <span className="text-ink-soft">{thesis}</span>
            </div>
          )}
          {reflection && (
            <div>
              <span className="text-ink-mute font-medium">Reflection: </span>
              <span className="text-ink-soft">{reflection}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function DecisionScorecardTab({
  decisions,
}: {
  decisions: TableRow<'decision_log'>[];
}) {
  const scorecard = useMemo(() => computeDecisionScorecard(decisions), [decisions]);
  // Resolved decisions only — the PM cares about calls that have a known outcome.
  const resolved = useMemo(
    () => decisions.filter((d) => d.status === 'resolved').sort((a, b) => (b.run_date ?? '').localeCompare(a.run_date ?? '')),
    [decisions]
  );

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
          color={scorecard.hitRatePct >= 50 ? 'text-up' : 'text-down'}
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
              ? 'text-ink-soft'
              : scorecard.calibrated
                ? 'text-up'
                : 'text-warn'
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
          <p className="text-xs text-ink-mute">
            Resolved decisions exist but none carry a recorded conviction, so calibration buckets
            cannot be formed.
          </p>
        )}
      </SectionCard>

      <SectionCard title="By conviction bucket" subtitle="Per-bucket sample size, hit rate, and mean conviction.">
        <div className="overflow-x-auto">
          <table className="w-full text-sm tabular-nums">
            <thead>
              <tr className="text-left text-xs text-ink-mute border-b border-hair">
                <th className="py-2 pr-4 font-medium">Bucket</th>
                <th className="py-2 pr-4 font-medium text-right">N</th>
                <th className="py-2 pr-4 font-medium text-right">Mean alpha</th>
                <th className="py-2 pr-4 font-medium text-right">Hit rate</th>
                <th className="py-2 font-medium text-right">Mean conviction</th>
              </tr>
            </thead>
            <tbody>
              {scorecard.buckets.map((b) => (
                <tr key={b.bucket} className="border-b border-hair/50">
                  <td className="py-2 pr-4 text-ink">{BUCKET_LABEL[b.bucket] ?? b.bucket}</td>
                  <td className="py-2 pr-4 text-right text-ink-soft">{b.n}</td>
                  <td className={`py-2 pr-4 text-right ${signColorClass(b.meanAlphaPct)}`}>
                    {fmtPct(b.meanAlphaPct)}
                  </td>
                  <td className="py-2 pr-4 text-right text-ink-soft">{b.hitRatePct.toFixed(1)}%</td>
                  <td className="py-2 text-right text-ink-soft">{b.meanConviction.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </SectionCard>

      {/* Per-decision drill-down — the PM's primary tool to evaluate the agent's reasoning.
          Shows every resolved call with its thesis (why the agent made the call) and reflection
          (what the agent learned at resolution time).  Sorted newest first. */}
      <SectionCard
        title="Resolved decisions"
        subtitle="Each resolved call with the agent's original thesis and post-mortem reflection. Expand a row to read the full reasoning."
      >
        {resolved.length ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm tabular-nums">
              <thead>
                <tr className="text-left text-xs text-ink-mute border-b border-hair">
                  <th className="py-2 pr-4 font-medium">Date</th>
                  <th className="py-2 pr-4 font-medium">Ticker</th>
                  <th className="py-2 pr-4 font-medium">Stance</th>
                  <th className="py-2 pr-4 font-medium text-right">Conviction</th>
                  <th className="py-2 pr-4 font-medium text-right">Return</th>
                  <th className="py-2 pr-4 font-medium text-right">Alpha</th>
                  <th className="py-2 font-medium">Reasoning</th>
                </tr>
              </thead>
              <tbody>
                {resolved.map((d) => (
                  <tr key={d.id} className="border-b border-hair/50 align-top">
                    <td className="py-2 pr-4 text-ink-mute text-xs">{d.run_date ?? '—'}</td>
                    <td className="py-2 pr-4 text-ink font-medium">{d.ticker}</td>
                    <td className="py-2 pr-4 text-ink-soft capitalize">{d.stance ?? '—'}</td>
                    <td className="py-2 pr-4 text-right text-ink-soft">
                      {d.conviction != null ? d.conviction.toFixed(1) : '—'}
                    </td>
                    <td className={`py-2 pr-4 text-right ${signColorClass(d.actual_return != null ? d.actual_return * 100 : null)}`}>
                      {fmtPct(d.actual_return != null ? d.actual_return * 100 : null)}
                    </td>
                    <td className={`py-2 pr-4 text-right ${signColorClass(d.alpha != null ? d.alpha * 100 : null)}`}>
                      {fmtPct(d.alpha != null ? d.alpha * 100 : null)}
                    </td>
                    <td className="py-2">
                      <ReasoningExpander thesis={d.thesis} reflection={d.reflection} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-xs text-ink-mute">No resolved decisions yet.</p>
        )}
      </SectionCard>
    </div>
  );
}
