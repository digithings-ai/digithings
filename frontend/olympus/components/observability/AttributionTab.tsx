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
import type { TableRow } from '@/lib/database.types';
import { EmptyState, SectionCard, StatTile, fmtPct, signColorClass } from './shared';
import { useChartColors, withAlpha } from '@/lib/chart-colors';

const TOP_N = 14;

function sum(values: Array<number | null | undefined>): number {
  return values.reduce<number>((acc, v) => acc + (v ?? 0), 0);
}

export default function AttributionTab({
  attribution,
  date,
  embedded = false,
}: {
  attribution: TableRow<'position_attribution'>[];
  date: string | null;
  embedded?: boolean;
}) {
  const chart = useChartColors();
  const summary = useMemo(() => {
    if (!attribution.length) return null;
    // Exclude the synthetic CASH row from all return sums — its total_attribution_pct
    // represents cash drag (allocation effect only) and inflates activeReturn when included.
    // The chart and holdings count already exclude CASH; these sums follow suit so every
    // number on the stat tiles is consistent.
    const holdings = attribution.filter((r) => r.ticker !== 'CASH');
    const activeReturn = sum(holdings.map((r) => r.total_attribution_pct));
    // Sort descending by date so the most-recent row wins the benchmark lookup, regardless of the
    // order rows arrived from the database.  An unsorted .find() is order-dependent and would
    // silently pick a stale benchmark if rows happen to arrive oldest-first.
    const sorted = [...attribution].sort((a, b) => (b.date ?? '').localeCompare(a.date ?? ''));
    const benchmarkReturn = sorted.find((r) => r.benchmark_return_pct != null)?.benchmark_return_pct ?? null;
    const portfolioReturn = benchmarkReturn != null ? activeReturn + benchmarkReturn : null;
    // Unpriced holdings (no window return) carry null attribution; the sums then under-count and
    // the active-return identity no longer reconciles — surface that rather than show a false total.
    const unpriced = holdings.filter((r) => r.total_attribution_pct == null).length;
    return { activeReturn, benchmarkReturn, portfolioReturn, holdings: holdings.length, unpriced };
  }, [attribution]);

  if (!summary) {
    return (
      <EmptyState
        title="No attribution rows yet"
        message="Per-position attribution is computed daily by refresh_attribution.py after EOD prices land, once the paper book holds positions. It will appear here after the next attribution run."
        note="Populates after the daily attribution job runs (refresh_attribution)."
        flat={embedded}
      />
    );
  }

  // Exclude the synthetic CASH row (contribution 0; its cash drag is in allocation/total) so the
  // "by position" chart stays aligned with the rest of the tab's holdings-only framing.
  const chartData = [...attribution]
    .filter((r) => r.ticker !== 'CASH' && r.contribution_pct != null)
    .sort((a, b) => Math.abs(b.contribution_pct ?? 0) - Math.abs(a.contribution_pct ?? 0))
    .slice(0, TOP_N)
    .map((r) => ({ ticker: r.ticker, contribution: r.contribution_pct as number }));

  return (
    <div className={`flex flex-col ${embedded ? 'gap-0' : 'gap-6'}`}>
      <div
        className={`grid grid-cols-2 lg:grid-cols-4 ${embedded ? 'gap-0 border-l border-t border-hair' : 'gap-3'}`}
      >
        <StatTile
          label="As of"
          value={date ?? '—'}
          sub={`${summary.holdings} ${summary.holdings === 1 ? 'holding' : 'holdings'}`}
          flat={embedded}
        />
        <StatTile
          label="Portfolio return"
          value={fmtPct(summary.portfolioReturn)}
          sub="window total"
          color={signColorClass(summary.portfolioReturn)}
          flat={embedded}
        />
        <StatTile
          label="Benchmark (SPY)"
          value={fmtPct(summary.benchmarkReturn)}
          color={signColorClass(summary.benchmarkReturn)}
          flat={embedded}
        />
        <StatTile
          label="Active return"
          value={fmtPct(summary.activeReturn)}
          sub={summary.unpriced > 0 ? `partial · ${summary.unpriced} unpriced` : 'Σ attribution'}
          color={signColorClass(summary.activeReturn)}
          flat={embedded}
        />
      </div>

      {summary.unpriced > 0 ? (
        <p className={`text-xs text-warn ${embedded ? 'border-b border-hair px-4 py-3' : ''}`}>
          {summary.unpriced} holding{summary.unpriced === 1 ? '' : 's'} lack a priced window, so the
          active-return total is partial and does not fully reconcile to portfolio − benchmark.
        </p>
      ) : null}

      <SectionCard
        title="Contribution by position"
        subtitle="Each holding's share of the portfolio's window return (weight × return). Top contributors and detractors."
        flat={embedded}
      >
        {chartData.length ? (
          <div className="h-[300px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
                <CartesianGrid stroke={chart.hair} vertical={false} />
                <XAxis dataKey="ticker" tick={{ fill: chart.axis, fontSize: 10 }} interval={0} angle={-30} textAnchor="end" height={50} />
                <YAxis tick={{ fill: chart.axis, fontSize: 11 }} tickFormatter={(v: number) => `${v}%`} />
                <Tooltip
                  cursor={{ fill: withAlpha(chart.ink, 0.04) }}
                  contentStyle={{
                    background: 'var(--term-bg)',
                    border: '1px solid var(--hair)',
                    borderRadius: 8,
                    fontSize: 12,
                  }}
                  formatter={(value: number) => [`${value}%`, 'Contribution']}
                />
                <Bar dataKey="contribution" radius={[3, 3, 0, 0]} isAnimationActive={false}>
                  {chartData.map((d) => (
                    <Cell key={d.ticker} fill={d.contribution >= 0 ? chart.up : chart.down} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <p className="text-xs text-ink-mute">No priced contributions to chart.</p>
        )}
      </SectionCard>

      <SectionCard
        title="Decomposition"
        subtitle="Single-benchmark attribution: contribution (weight × return), selection (weight × excess vs SPY), and total active. Sums reconcile to active return when every holding is priced."
        flat={embedded}
      >
        <div className="overflow-x-auto">
          <table className="w-full text-sm tabular-nums">
            <thead>
              <tr className="text-left text-xs text-ink-mute border-b border-hair">
                <th className="py-2 pr-4 font-medium">Ticker</th>
                <th className="py-2 pr-4 font-medium">Sector</th>
                <th className="py-2 pr-4 font-medium text-right">Weight</th>
                <th className="py-2 pr-4 font-medium text-right">Return</th>
                <th className="py-2 pr-4 font-medium text-right">Contribution</th>
                <th className="py-2 pr-4 font-medium text-right">Selection</th>
                <th className="py-2 font-medium text-right">Total</th>
              </tr>
            </thead>
            <tbody>
              {attribution.map((r) => (
                <tr key={r.id} className="border-b border-hair/50">
                  <td className="py-2 pr-4 text-ink">{r.ticker}</td>
                  <td className="py-2 pr-4 text-ink-mute truncate max-w-[160px]">{r.sector_bucket ?? '—'}</td>
                  <td className="py-2 pr-4 text-right text-ink-soft">{fmtPct(r.weight_pct, 1)}</td>
                  <td className={`py-2 pr-4 text-right ${signColorClass(r.position_return_pct)}`}>
                    {fmtPct(r.position_return_pct)}
                  </td>
                  <td className={`py-2 pr-4 text-right ${signColorClass(r.contribution_pct)}`}>
                    {fmtPct(r.contribution_pct)}
                  </td>
                  <td className={`py-2 pr-4 text-right ${signColorClass(r.selection_effect_pct)}`}>
                    {fmtPct(r.selection_effect_pct)}
                  </td>
                  <td className={`py-2 text-right ${signColorClass(r.total_attribution_pct)}`}>
                    {fmtPct(r.total_attribution_pct)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </SectionCard>
    </div>
  );
}
