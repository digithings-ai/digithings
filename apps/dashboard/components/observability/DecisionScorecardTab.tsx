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
import type { TableRow as DbTableRow } from '@/lib/database.types';
import { SectionCard, StatTile, fmtPct, signColorClass } from './shared';
import { useChartColors, withAlpha } from '@/lib/chart-colors';
import {
  Button,
  EmptyState,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@digithings/ui/ui';

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
      <Button
        variant="link"
        size="xs"
        onClick={() => setOpen((v) => !v)}
        className="h-auto justify-start p-0 text-xs text-ink-soft underline underline-offset-2 decoration-dotted hover:text-ink text-left"
        aria-expanded={open}
      >
        {open ? 'hide' : 'show reasoning'}
      </Button>
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
  decisions: DbTableRow<'decision_log'>[];
}) {
  const chart = useChartColors();
  const scorecard = useMemo(() => computeDecisionScorecard(decisions), [decisions]);
  // Resolved decisions only — the PM cares about calls that have a known outcome.
  const resolved = useMemo(
    () => decisions.filter((d) => d.status === 'resolved').sort((a, b) => (b.run_date ?? '').localeCompare(a.run_date ?? '')),
    [decisions]
  );

  if (!scorecard) {
    return (
      <EmptyState
        dress="glass"
        data-reveal
        title="No resolved decisions yet"
        body="The scorecard scores each analyst call once its holding window elapses and the resolver records realized alpha vs SPY. Decisions are still pending — check back after the next resolution run."
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
                <CartesianGrid stroke={chart.hair} vertical={false} />
                <XAxis dataKey="bucket" tick={{ fill: chart.axis, fontSize: 11 }} />
                <YAxis
                  tick={{ fill: chart.axis, fontSize: 11 }}
                  tickFormatter={(v: number) => `${v}%`}
                />
                <Tooltip
                  cursor={{ fill: withAlpha(chart.ink, 0.04) }}
                  contentStyle={{
                    background: 'var(--term-bg)',
                    border: '1px solid var(--hair)',
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
                    <Cell key={d.bucket} fill={d.meanAlphaPct >= 0 ? chart.up : chart.down} />
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
        <Table className="text-sm tabular-nums">
          <TableHeader>
            <TableRow className="text-left text-xs text-ink-mute border-hair hover:bg-transparent">
              <TableHead className="h-auto py-2 pr-4 font-medium">Bucket</TableHead>
              <TableHead numeric className="h-auto py-2 pr-4 font-medium">N</TableHead>
              <TableHead numeric className="h-auto py-2 pr-4 font-medium">Mean alpha</TableHead>
              <TableHead numeric className="h-auto py-2 pr-4 font-medium">Hit rate</TableHead>
              <TableHead numeric className="h-auto py-2 font-medium">Mean conviction</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {scorecard.buckets.map((b) => (
              <TableRow key={b.bucket} className="border-hair/50">
                <TableCell className="py-2 pr-4 text-ink">{BUCKET_LABEL[b.bucket] ?? b.bucket}</TableCell>
                <TableCell numeric className="py-2 pr-4 text-ink-soft">{b.n}</TableCell>
                <TableCell numeric className={`py-2 pr-4 ${signColorClass(b.meanAlphaPct)}`}>
                  {fmtPct(b.meanAlphaPct)}
                </TableCell>
                <TableCell numeric className="py-2 pr-4 text-ink-soft">{b.hitRatePct.toFixed(1)}%</TableCell>
                <TableCell numeric className="py-2 text-ink-soft">{b.meanConviction.toFixed(2)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </SectionCard>

      {/* Per-decision drill-down — the PM's primary tool to evaluate the agent's reasoning.
          Shows every resolved call with its thesis (why the agent made the call) and reflection
          (what the agent learned at resolution time).  Sorted newest first. */}
      <SectionCard
        title="Resolved decisions"
        subtitle="Each resolved call with the agent's original thesis and post-mortem reflection. Expand a row to read the full reasoning."
      >
        {resolved.length ? (
          <Table className="text-sm tabular-nums">
            <TableHeader>
              <TableRow className="text-left text-xs text-ink-mute border-hair hover:bg-transparent">
                <TableHead className="h-auto py-2 pr-4 font-medium">Date</TableHead>
                <TableHead className="h-auto py-2 pr-4 font-medium">Ticker</TableHead>
                <TableHead className="h-auto py-2 pr-4 font-medium">Stance</TableHead>
                <TableHead numeric className="h-auto py-2 pr-4 font-medium">Conviction</TableHead>
                <TableHead numeric className="h-auto py-2 pr-4 font-medium">Return</TableHead>
                <TableHead numeric className="h-auto py-2 pr-4 font-medium">Alpha</TableHead>
                <TableHead className="h-auto py-2 font-medium">Reasoning</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {resolved.map((d) => (
                <TableRow key={d.id} className="border-hair/50 align-top">
                  <TableCell className="py-2 pr-4 text-ink-mute text-xs">{d.run_date ?? '—'}</TableCell>
                  <TableCell className="py-2 pr-4 text-ink font-medium">{d.ticker}</TableCell>
                  <TableCell className="py-2 pr-4 text-ink-soft capitalize">{d.stance ?? '—'}</TableCell>
                  <TableCell numeric className="py-2 pr-4 text-ink-soft">
                    {d.conviction != null ? d.conviction.toFixed(1) : '—'}
                  </TableCell>
                  <TableCell numeric className={`py-2 pr-4 ${signColorClass(d.actual_return != null ? d.actual_return * 100 : null)}`}>
                    {fmtPct(d.actual_return != null ? d.actual_return * 100 : null)}
                  </TableCell>
                  <TableCell numeric className={`py-2 pr-4 ${signColorClass(d.alpha != null ? d.alpha * 100 : null)}`}>
                    {fmtPct(d.alpha != null ? d.alpha * 100 : null)}
                  </TableCell>
                  <TableCell className="py-2 whitespace-normal">
                    <ReasoningExpander thesis={d.thesis} reflection={d.reflection} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : (
          <p className="text-xs text-ink-mute">No resolved decisions yet.</p>
        )}
      </SectionCard>
    </div>
  );
}
