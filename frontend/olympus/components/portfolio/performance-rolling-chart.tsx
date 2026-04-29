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
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 rounded-lg border border-border-subtle bg-bg-secondary/50 p-4">
      <div>
        <p className="text-[10px] text-text-muted uppercase tracking-wider mb-1">Sharpe (Rf = 0)</p>
        <p className="text-lg font-semibold tabular-nums text-text-primary">{sharpe.toFixed(2)}</p>
      </div>
      <div>
        <p className="text-[10px] text-text-muted uppercase tracking-wider mb-1">Sortino</p>
        <p className="text-lg font-semibold tabular-nums text-text-primary">{sortino.toFixed(2)}</p>
      </div>
      <div>
        <p className="text-[10px] text-text-muted uppercase tracking-wider mb-1">Ann. volatility</p>
        <p className="text-lg font-semibold tabular-nums text-text-primary">{annVolPct.toFixed(1)}%</p>
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
  const period = computeRiskRatiosFromNavSnaps(snaps);
  const hasRollingSharpe = data.some((d) => d.sharpe != null && !Number.isNaN(d.sharpe));
  const rollingPoints = data.filter((d) => d.sharpe != null && !Number.isNaN(d.sharpe)).length;

  return (
    <div className="space-y-4">
      {period ? (
        <>
          <PeriodRiskSummary sharpe={period.sharpe} sortino={period.sortino} annVolPct={period.annVolPct} />
          <p className="text-[11px] text-text-muted leading-snug">
            Full selected range — same methodology as Advanced statistics (daily returns, Rf = 0).
          </p>
        </>
      ) : (
        <p className="text-sm text-text-muted">Need at least two NAV observations in this range.</p>
      )}

      {hasRollingSharpe && rollingPoints >= 2 ? (
        <div className="space-y-2">
          <p className="text-[11px] text-text-muted">
            Rolling series uses a {rollingWindow}-trading-day window (shortened automatically when history is
            limited).
          </p>
          <div className="h-[min(400px,50vh)] min-h-[280px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
                <CartesianGrid stroke="rgba(255,255,255,0.05)" />
                <XAxis
                  dataKey="date"
                  tick={{ fill: '#71717a', fontSize: 11 }}
                  tickFormatter={(d: string) => d?.slice(5)}
                />
                <YAxis
                  yAxisId="sharpe"
                  tick={{ fill: '#71717a', fontSize: 11 }}
                  label={{ value: 'Sharpe', angle: -90, position: 'insideLeft', fill: '#71717a', fontSize: 10 }}
                />
                <YAxis
                  yAxisId="vol"
                  orientation="right"
                  tick={{ fill: '#71717a', fontSize: 11 }}
                  tickFormatter={(v) => `${v}%`}
                  label={{
                    value: 'Ann. vol',
                    angle: 90,
                    position: 'insideRight',
                    fill: '#71717a',
                    fontSize: 10,
                  }}
                />
                <Tooltip
                  contentStyle={{
                    background: '#1a1a1a',
                    border: '1px solid #2a2a2a',
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
                  stroke="#8b5cf6"
                  strokeWidth={2}
                  dot={false}
                  connectNulls
                />
                <Line
                  yAxisId="vol"
                  type="monotone"
                  dataKey="volAnn"
                  name="Rolling vol (ann.)"
                  stroke="#06b6d4"
                  strokeWidth={1.5}
                  dot={false}
                  connectNulls
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      ) : period ? (
        <p className="text-[12px] text-text-muted rounded-lg border border-dashed border-border-subtle px-4 py-3">
          Not enough overlapping days in this range for rolling metrics.
        </p>
      ) : null}
    </div>
  );
}
