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

export function PerformanceDrawdownChart({
  data,
}: {
  data: Array<{ date: string; drawdown: number }>;
}) {
  if (data.length < 2) {
    return (
      <div className="h-[240px] flex items-center justify-center text-text-muted text-sm">
        Not enough NAV history for drawdown.
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid stroke="rgba(255,255,255,0.05)" />
        <XAxis
          dataKey="date"
          tick={{ fill: '#71717a', fontSize: 11 }}
          tickFormatter={(d: string) => d?.slice(5)}
        />
        <YAxis
          tick={{ fill: '#71717a', fontSize: 11 }}
          domain={['auto', 0]}
          tickFormatter={(v: number) => `${v.toFixed(0)}%`}
        />
        <Tooltip
          contentStyle={{
            background: '#1a1a1a',
            border: '1px solid #2a2a2a',
            borderRadius: '8px',
            fontSize: '0.85rem',
          }}
          formatter={(val: number) => [`${Number(val).toFixed(2)}%`, 'Drawdown']}
        />
        <Area
          type="monotone"
          dataKey="drawdown"
          name="Drawdown"
          stroke="#ef4444"
          fill="rgba(239,68,68,0.15)"
          strokeWidth={2}
          dot={false}
          connectNulls
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
}
