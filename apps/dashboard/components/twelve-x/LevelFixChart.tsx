'use client';

import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { useChartColors } from '@/lib/chart-colors';
import type { LevelFixSeries } from '@/lib/twelve-x/level-vs-fix';

function fmtFix(v: number | null): string {
  if (v === null || !Number.isFinite(v)) return '—';
  return v >= 100 ? v.toFixed(1) : v.toFixed(4);
}

/**
 * Published levels vs the moving fix for one idea: flat entry band
 * (ReferenceArea), stop + target ReferenceLines, the fix Line, and entry/exit
 * anchor dots when the eval row supplies them. Text captions carry the same
 * facts so the chart stays legible (and testable) without pixels.
 */
export function LevelFixChart({ series }: { series: LevelFixSeries }) {
  const chart = useChartColors();
  const {
    pair,
    entryLow,
    entryHigh,
    stop,
    targets,
    entryDate,
    exitDate,
    entryFix,
    exitFix,
    points,
    anchorsOnly,
  } = series;

  const data = points.map((p) => ({ date: p.date, fix: p.fix }));
  const entryMarker =
    entryDate && entryFix !== null ? { date: entryDate, fix: entryFix } : null;
  const exitMarker =
    exitDate && exitFix !== null ? { date: exitDate, fix: exitFix } : null;

  const hasLevels = entryLow !== null || entryHigh !== null || stop !== null || targets.length > 0;

  if (data.length === 0 && !hasLevels) {
    return (
      <div className="border border-hair bg-surface/40 p-4 text-xs text-ink-mute" data-testid="level-fix-chart">
        No fix data for {pair} yet.
      </div>
    );
  }

  return (
    <div className="space-y-1.5" data-testid="level-fix-chart">
      <p className="font-mono text-[11px] text-ink-soft">
        {pair} fix vs published levels
        {anchorsOnly ? ' · anchors only' : ''}
      </p>
      {data.length > 0 ? (
        <div className="h-[220px] w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
              <CartesianGrid stroke={chart.hair} />
              {entryLow !== null && entryHigh !== null ? (
                <ReferenceArea y1={entryLow} y2={entryHigh} fill={chart.accent} fillOpacity={0.08} />
              ) : null}
              {stop !== null ? (
                <ReferenceLine y={stop} stroke={chart.warn} strokeDasharray="4 4" />
              ) : null}
              {targets.map((t, i) => (
                <ReferenceLine
                  key={`${t}-${i}`}
                  y={t}
                  stroke={chart.accent}
                  strokeOpacity={0.6}
                  strokeDasharray="2 4"
                />
              ))}
              <XAxis
                dataKey="date"
                tick={{ fill: chart.axis, fontSize: 10 }}
                tickFormatter={(d: string) => d?.slice(5)}
                minTickGap={28}
              />
              <YAxis
                domain={['auto', 'auto']}
                tick={{ fill: chart.axis, fontSize: 10 }}
                tickFormatter={(v: number) => fmtFix(v)}
                width={64}
              />
              <Tooltip
                contentStyle={{
                  background: 'var(--term-bg)',
                  border: '1px solid var(--hair)',
                  color: 'var(--ink)',
                  borderRadius: 0,
                  fontSize: '0.8rem',
                }}
                formatter={(val) => {
                  const n = typeof val === 'number' ? val : Number(val);
                  return [Number.isNaN(n) ? '—' : fmtFix(n), 'Fix'];
                }}
              />
              <Line type="monotone" dataKey="fix" stroke={chart.ink} strokeWidth={1.5} dot={false} />
              {entryMarker ? (
                <ReferenceDot
                  x={entryMarker.date}
                  y={entryMarker.fix}
                  r={3}
                  fill={chart.accent}
                  stroke="var(--term-bg)"
                />
              ) : null}
              {exitMarker ? (
                <ReferenceDot
                  x={exitMarker.date}
                  y={exitMarker.fix}
                  r={3}
                  fill={chart.warn}
                  stroke="var(--term-bg)"
                />
              ) : null}
            </LineChart>
          </ResponsiveContainer>
        </div>
      ) : null}
      <p className="font-mono text-[10px] text-ink-mute">
        Entry {entryLow !== null && entryHigh !== null
          ? `${fmtFix(entryLow)}–${fmtFix(entryHigh)}`
          : entryLow !== null
            ? fmtFix(entryLow)
            : entryHigh !== null
              ? fmtFix(entryHigh)
              : '—'}
        {' · '}Stop {fmtFix(stop)}
        {targets.length > 0 ? ` · Targets ${targets.map(fmtFix).join(', ')}` : ''}
        {entryMarker ? ` · In ${fmtFix(entryMarker.fix)}` : ''}
        {exitMarker ? ` · Out ${fmtFix(exitMarker.fix)}` : ''}
      </p>
    </div>
  );
}

export default LevelFixChart;
