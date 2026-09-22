'use client';

import { TimeSeries } from '@digithings/ui';
import type { LevelFixSeries } from '@/lib/twelve-x/level-vs-fix';

function fmtFix(v: number | null): string {
  if (v === null || !Number.isFinite(v)) return '—';
  return v >= 100 ? v.toFixed(1) : v.toFixed(4);
}

/**
 * Published levels vs the moving fix for one idea: flat entry band, stop +
 * target lines, the fix series, and entry/exit anchor dots when the eval row
 * supplies them. Rides the kit TimeSeries reference overlays (Q3b slice 5a,
 * #4443) — token-driven SVG, so no theme-color reader is needed. Text
 * captions carry the same facts so the chart stays legible (and testable)
 * without pixels.
 */
export function LevelFixChart({ series }: { series: LevelFixSeries }) {
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

  const hasLevels = entryLow !== null || entryHigh !== null || stop !== null || targets.length > 0;

  // The chart's whole purpose is where the fix sits relative to the published
  // levels, so the domain must cover both. Without it the frame auto-derives
  // from the fixes alone and an out-of-range stop/target clamps to the plot
  // edge, which reads as "at the boundary" regardless of the real level.
  const levelValues = [entryLow, entryHigh, stop, ...targets].filter(
    (v): v is number => v !== null,
  );
  const spanValues = [...points.map((p) => p.fix), ...levelValues];
  const domain: [number, number] | undefined = (() => {
    if (spanValues.length === 0) return undefined;
    const lo = Math.min(...spanValues);
    const hi = Math.max(...spanValues);
    // A flat series would give a zero-width domain (NaN in the path), so the
    // pad is always positive: 8% of the spread, or 1% of the value when flat.
    const pad = hi > lo ? (hi - lo) * 0.08 : Math.abs(hi) * 0.01 || 0.01;
    return [lo - pad, hi + pad];
  })();

  if (points.length === 0 && !hasLevels) {
    return (
      <div className="border border-hair p-4 text-xs text-ink-mute" data-testid="level-fix-chart">
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
      {points.length > 0 ? (
        <div className="h-[220px] w-full">
          <TimeSeries
            points={points.map((p) => ({ t: p.date, v: p.fix }))}
            height={220}
                fmt={fmtFix}
                domain={domain}

            references={{
              bands:
                entryLow !== null && entryHigh !== null
                  ? [{ from: entryLow, to: entryHigh, tone: 'accent' as const }]
                  : [],
              lines: [
                ...(stop !== null
                  ? [{ value: stop, tone: 'warn' as const, label: `Stop ${fmtFix(stop)}` }]
                  : []),
                ...targets.map((t) => ({
                  value: t,
                  tone: 'accent' as const,
                  label: `Target ${fmtFix(t)}`,
                })),
              ],
              markers: [
                ...(entryDate && entryFix !== null
                  ? [{ t: entryDate, v: entryFix, tone: 'accent' as const, label: `In ${fmtFix(entryFix)}` }]
                  : []),
                ...(exitDate && exitFix !== null
                  ? [{ t: exitDate, v: exitFix, tone: 'warn' as const, label: `Out ${fmtFix(exitFix)}` }]
                  : []),
              ],
            }}
            ariaLabel={`${pair} fix vs published levels`}
          />
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
        {entryDate && entryFix !== null ? ` · In ${fmtFix(entryFix)}` : ''}
        {exitDate && exitFix !== null ? ` · Out ${fmtFix(exitFix)}` : ''}
      </p>
    </div>
  );
}

export default LevelFixChart;
