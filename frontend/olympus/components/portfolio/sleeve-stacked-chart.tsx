'use client';

import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts';

const PALETTE = [
  '#3B82F6',
  '#10B981',
  '#F59E0B',
  '#EF4444',
  '#8B5CF6',
  '#06B6D4',
  '#F97316',
  '#EC4899',
  '#6366F1',
  '#14B8A6',
];

function SleeveTooltipBody({
  active,
  payload,
  label,
  seriesKeys,
  formatKey,
}: {
  active?: boolean;
  payload?: Array<{ payload?: Record<string, unknown> }>;
  label?: string | number;
  seriesKeys: string[];
  formatKey: (key: string) => string;
}) {
  if (!active || !payload?.length) return null;
  const row = payload[0]?.payload;
  if (!row) return null;
  const date = String(label ?? row.date ?? '');
  const entries = seriesKeys
    .map((k) => ({ k, v: Number(row[k] ?? 0) }))
    .filter((x) => x.v > 0.004)
    .sort((a, b) => b.v - a.v);
  if (!entries.length) return null;

  return (
    <div className="rounded-lg border border-border-subtle bg-[#141414] px-3 py-2 text-xs shadow-lg min-w-[160px]">
      <p className="font-medium text-text-primary mb-1.5 font-mono">{date}</p>
      <ul className="space-y-0.5 max-h-48 overflow-y-auto">
        {entries.map(({ k, v }) => (
          <li key={k} className="flex justify-between gap-4 tabular-nums">
            <span className="text-text-secondary truncate">{formatKey(k)}</span>
            <span className="text-text-primary shrink-0">{v.toFixed(1)}%</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

interface SleeveStackedChartProps {
  data: Array<Record<string, number | string>>;
  keys: string[];
  formatKey: (key: string) => string;
  /** Highlight the selected snapshot date (synced with PM artifacts / URL). */
  selectedDate?: string | null;
  /** Fired when the user clicks the chart at a date (locks selection). */
  onChartDateSelect?: (isoDate: string) => void;
}

type ChartClickState = {
  activeLabel?: string | number;
  activeTooltipIndex?: number;
};

export function SleeveStackedChart({
  data,
  keys,
  formatKey,
  selectedDate,
  onChartDateSelect,
}: SleeveStackedChartProps) {
  if (!data.length || !keys.length) {
    return (
      <div className="h-[320px] flex items-center justify-center text-text-muted text-sm">
        Not enough history to chart sleeves.
      </div>
    );
  }

  const dateSet = new Set(data.map((row) => String(row.date ?? '')));

  function handleChartClick(state: unknown) {
    if (!onChartDateSelect) return;
    const s = state as ChartClickState | null | undefined;
    let iso: string | null = null;
    if (s?.activeLabel != null) {
      const cand = String(s.activeLabel);
      if (dateSet.has(cand)) iso = cand;
    }
    if (!iso && s?.activeTooltipIndex != null && data[s.activeTooltipIndex]) {
      const row = data[s.activeTooltipIndex];
      const d = String(row.date ?? '');
      if (dateSet.has(d)) iso = d;
    }
    if (iso) onChartDateSelect(iso);
  }

  return (
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart
        data={data}
        margin={{ top: 8, right: 8, left: 0, bottom: 0 }}
        onClick={onChartDateSelect ? handleChartClick : undefined}
      >
        <CartesianGrid stroke="rgba(255,255,255,0.05)" />
        <XAxis
          dataKey="date"
          tick={{ fill: '#71717a', fontSize: 11 }}
          tickFormatter={(d: string) => d?.slice(5)}
        />
        <YAxis tick={{ fill: '#71717a', fontSize: 11 }} domain={[0, 100]} tickFormatter={(v) => `${v}%`} />
        <Tooltip
          content={(props) => (
            <SleeveTooltipBody {...props} seriesKeys={keys} formatKey={formatKey} />
          )}
        />
        <Legend formatter={(value: string) => <span className="text-text-secondary text-xs">{value}</span>} />
        {selectedDate && dateSet.has(selectedDate) ? (
          <ReferenceLine
            x={selectedDate}
            stroke="rgba(96, 165, 250, 0.9)"
            strokeDasharray="4 4"
            strokeWidth={1}
          />
        ) : null}
        {keys.map((k, i) => (
          <Area
            key={k}
            type="monotone"
            dataKey={k}
            stackId="sleeves"
            stroke={PALETTE[i % PALETTE.length]}
            fill={PALETTE[i % PALETTE.length]}
            fillOpacity={0.65}
            name={formatKey(k)}
            connectNulls
          />
        ))}
      </AreaChart>
    </ResponsiveContainer>
  );
}
