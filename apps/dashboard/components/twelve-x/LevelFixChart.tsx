'use client';

import { RangeTrack, Sparkline } from '@digithings/ui/ui';
import { levelFixRange, type LevelFixSeries } from '@/lib/twelve-x/level-vs-fix';

function fmtFix(v: number | null): string {
  if (v === null || !Number.isFinite(v)) return '—';
  return v >= 100 ? v.toFixed(1) : v.toFixed(4);
}

/**
 * Published levels vs the moving fix for one idea: the fix history as a
 * sparkline and the entry zone / stop / targets / latest fix as markers on one
 * shared range track. The caption carries the same numbers as text so the
 * chart stays legible (and testable) without pixels.
 */
export function LevelFixChart({ series }: { series: LevelFixSeries }) {
  const { pair, entryLow, entryHigh, stop, targets, entryDate, exitDate, entryFix, exitFix, points, anchorsOnly } =
    series;

  const entryMarker = entryDate && entryFix !== null ? { date: entryDate, fix: entryFix } : null;
  const exitMarker = exitDate && exitFix !== null ? { date: exitDate, fix: exitFix } : null;
  const hasLevels = entryLow !== null || entryHigh !== null || stop !== null || targets.length > 0;

  if (points.length === 0 && !hasLevels) {
    return (
      <div className="border border-hair bg-surface/40 p-4 text-xs text-ink-mute" data-testid="level-fix-chart">
        No fix data for {pair} yet.
      </div>
    );
  }

  const range = levelFixRange(series);

  return (
    <div className="space-y-1.5" data-testid="level-fix-chart">
      <p className="font-mono text-[11px] text-ink-soft">
        {pair} fix vs published levels
        {anchorsOnly ? ' · anchors only' : ''}
      </p>
      {points.length > 1 ? (
        <Sparkline
          values={points.map((p) => p.fix)}
          tone="ink"
          area
          lastDot={false}
          height={56}
          preserveAspectRatio="none"
          className="block h-14 w-full"
          label={`${pair} fix, ${points.length} sessions from ${fmtFix(points[0].fix)} to ${fmtFix(points[points.length - 1].fix)}`}
        />
      ) : null}
      {range ? (
        <RangeTrack
          low={range.low}
          high={range.high}
          label={`${pair} published levels and latest fix`}
          markers={range.markers}
          format={fmtFix}
          showEnds
        />
      ) : null}
      <p className="font-mono text-[10px] text-ink-mute">
        Entry{' '}
        {entryLow !== null && entryHigh !== null
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
