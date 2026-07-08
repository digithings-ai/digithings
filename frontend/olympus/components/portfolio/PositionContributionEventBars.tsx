'use client';

import {
  Bar,
  BarChart,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { useChartColors, withAlpha } from '@/lib/chart-colors';

export interface EventBarDatum {
  name: string;
  deltaPp: number;
  fill: string;
}

/**
 * "Δ ppt between activity dates" — one horizontal bar per activity leg.
 * CATEGORICAL (bars keyed by event label, not by trading day), so it stays on
 * recharts under the lib/CHARTS.md ruling (#1420). Extracted verbatim from
 * PositionContributionChart when its time-series pane moved to
 * lightweight-charts.
 */
export function PositionContributionEventBars({
  data,
  tickDecimals,
}: {
  data: EventBarDatum[];
  tickDecimals: number;
}) {
  const chart = useChartColors();
  if (!data.length) return null;
  return (
    <div className="border-t border-hair px-4 py-4">
      <p className="text-[11px] text-ink-mute uppercase tracking-wider">Δ ppt between activity dates</p>
      <p className="text-[11px] text-ink-mute mt-1 mb-3 leading-snug">
        Each bar is the change in cumulative portfolio attribution (ppt) from the prior step to this activity
        (NAV-aligned). Green / red = contribution added or lost in that leg.
      </p>
      <div
        className="w-full"
        style={{ height: Math.min(280, Math.max(120, data.length * 36)) }}
      >
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            layout="vertical"
            data={data}
            margin={{ top: 4, right: 28, left: 4, bottom: 4 }}
          >
            <XAxis
              type="number"
              tick={{ fill: chart.axis, fontSize: 10 }}
              tickFormatter={(v) => (typeof v === 'number' ? v.toFixed(tickDecimals) : String(v))}
            />
            <YAxis
              type="category"
              dataKey="name"
              width={200}
              tick={{ fill: chart.inkSoft, fontSize: 10 }}
              interval={0}
            />
            <Tooltip
              cursor={{ fill: withAlpha(chart.ink, 0.03) }}
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null;
                const row = payload[0].payload as { name: string; deltaPp: number };
                return (
                  <div className="rounded-lg border border-hair bg-term-bg px-3 py-2 text-[0.82rem] shadow-lg max-w-sm">
                    <p className="text-ink-soft text-[11px] leading-snug">{row.name}</p>
                    <p className="text-ink tabular-nums mt-1 font-mono">
                      Δ {row.deltaPp >= 0 ? '+' : ''}
                      {row.deltaPp.toFixed(4)} ppt
                    </p>
                  </div>
                );
              }}
            />
            <ReferenceLine x={0} stroke={withAlpha(chart.ink, 0.12)} />
            <Bar dataKey="deltaPp" radius={[0, 2, 2, 0]} isAnimationActive={false}>
              {data.map((entry, i) => (
                <Cell key={`cell-${i}`} fill={entry.fill} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
