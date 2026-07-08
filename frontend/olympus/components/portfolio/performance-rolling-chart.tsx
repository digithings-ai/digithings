'use client';

import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { NavChartPoint } from '@/lib/types';
import { computeRiskRatiosFromNavSnaps } from '@/lib/portfolio-risk-metrics';
import { ROLLING_SERIES, useChartColors } from '@/lib/chart-colors';

function PeriodRiskSummary({
  sharpe,
  sortino,
  annVolPct,
}: {
  sharpe: number;
  sortino: number;
  annVolPct: number;
}) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 rounded-lg border border-hair bg-term-bg/50 p-4">
      <div>
        <p className="text-[10px] text-ink-mute uppercase tracking-wider mb-1">Sharpe (Rf = 0)</p>
        <p className="text-lg font-semibold tabular-nums text-ink">{sharpe.toFixed(2)}</p>
      </div>
      <div>
        <p className="text-[10px] text-ink-mute uppercase tracking-wider mb-1">Sortino</p>
        <p className="text-lg font-semibold tabular-nums text-ink">{sortino.toFixed(2)}</p>
      </div>
      <div>
        <p className="text-[10px] text-ink-mute uppercase tracking-wider mb-1">Ann. volatility</p>
        <p className="text-lg font-semibold tabular-nums text-ink">{annVolPct.toFixed(1)}%</p>
      </div>
    </div>
  );
}

export function PerformanceRollingChart({
  data,
  snaps,
  rollingWindow,
}: {
  data: Array<{ date: string; sharpe: number | null; volAnn: number | null }>;
  snaps: NavChartPoint[];
  rollingWindow: number;
}) {
  const chart = useChartColors();
  const period = computeRiskRatiosFromNavSnaps(snaps);
  const hasRollingSharpe = data.some((d) => d.sharpe != null && !Number.isNaN(d.sharpe));
  const rollingPoints = data.filter((d) => d.sharpe != null && !Number.isNaN(d.sharpe)).length;

  return (
    <div className="space-y-4">
      {period ? (
        <>
          <PeriodRiskSummary sharpe={period.sharpe} sortino={period.sortino} annVolPct={period.annVolPct} />
          <p className="text-[11px] text-ink-mute leading-snug">
            Full selected range — same methodology as Advanced statistics (daily returns, Rf = 0).
          </p>
        </>
      ) : (
        <p className="text-sm text-ink-mute">Need at least two NAV observations in this range.</p>
      )}

      {hasRollingSharpe && rollingPoints >= 2 ? (
        <div className="space-y-2">
          <p className="text-[11px] text-ink-mute">
            Rolling series uses a {rollingWindow}-trading-day window (shortened automatically when history is
            limited).
          </p>
          <div className="h-[min(400px,50vh)] min-h-[280px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
                <CartesianGrid stroke={chart.hair} />
                <XAxis
                  dataKey="date"
                  tick={{ fill: chart.axis, fontSize: 11 }}
                  tickFormatter={(d: string) => d?.slice(5)}
                />
                <YAxis
                  yAxisId="sharpe"
                  tick={{ fill: chart.axis, fontSize: 11 }}
                  label={{ value: 'Sharpe', angle: -90, position: 'insideLeft', fill: chart.axis, fontSize: 10 }}
                />
                <YAxis
                  yAxisId="vol"
                  orientation="right"
                  tick={{ fill: chart.axis, fontSize: 11 }}
                  tickFormatter={(v) => `${v}%`}
                  label={{
                    value: 'Ann. vol',
                    angle: 90,
                    position: 'insideRight',
                    fill: chart.axis,
                    fontSize: 10,
                  }}
                />
                <Tooltip
                  contentStyle={{
                    background: 'var(--term-bg)',
                    border: '1px solid var(--hair)',
                    color: 'var(--ink)',
                    borderRadius: '8px',
                    fontSize: '0.85rem',
                  }}
                  formatter={(val, name) => {
                    const n = typeof val === 'number' ? val : val != null ? Number(val) : NaN;
                    const nm = String(name);
                    if (Number.isNaN(n)) return ['—', nm];
                    if (nm === 'Rolling vol (ann.)') return [`${n.toFixed(1)}%`, nm];
                    return [n.toFixed(2), nm];
                  }}
                />
                <Legend />
                <Line
                  yAxisId="sharpe"
                  type="monotone"
                  dataKey="sharpe"
                  name={`Rolling Sharpe (${rollingWindow}d)`}
                  stroke={ROLLING_SERIES.sharpe}
                  strokeWidth={2}
                  dot={false}
                  connectNulls
                />
                <Line
                  yAxisId="vol"
                  type="monotone"
                  dataKey="volAnn"
                  name="Rolling vol (ann.)"
                  stroke={ROLLING_SERIES.vol}
                  strokeWidth={1.5}
                  dot={false}
                  connectNulls
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      ) : period ? (
        <p className="text-[12px] text-ink-mute rounded-lg border border-dashed border-hair px-4 py-3">
          Not enough overlapping days in this range for rolling metrics.
        </p>
      ) : null}
    </div>
  );
}
