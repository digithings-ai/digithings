'use client';

import {
  Area,
  CartesianGrid,
  ComposedChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { useChartColors, withAlpha } from '@/lib/chart-colors';

export function PerformanceDrawdownChart({
  data,
}: {
  data: Array<{ date: string; drawdown: number }>;
}) {
  const chart = useChartColors();
  if (data.length < 2) {
    return (
      <div className="h-[240px] flex items-center justify-center text-ink-mute text-sm">
        Not enough NAV history for drawdown.
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid stroke={chart.hair} />
        <XAxis
          dataKey="date"
          tick={{ fill: chart.axis, fontSize: 11 }}
          tickFormatter={(d: string) => d?.slice(5)}
        />
        <YAxis
          tick={{ fill: chart.axis, fontSize: 11 }}
          domain={['auto', 0]}
          tickFormatter={(v: number) => `${v.toFixed(0)}%`}
        />
        <Tooltip
          contentStyle={{
            background: 'var(--term-bg)',
            border: '1px solid var(--hair)',
            color: 'var(--ink)',
            borderRadius: '8px',
            fontSize: '0.85rem',
          }}
          formatter={(val: number) => [`${Number(val).toFixed(2)}%`, 'Drawdown']}
        />
        <Area
          type="monotone"
          dataKey="drawdown"
          name="Drawdown"
          stroke={chart.down}
          fill={withAlpha(chart.down, 0.15)}
          strokeWidth={2}
          dot={false}
          connectNulls
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
}
