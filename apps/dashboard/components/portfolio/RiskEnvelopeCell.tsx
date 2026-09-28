'use client';

import { formatQuoteAge, type Valuation } from '@/lib/live-valuation';

/**
 * Advisory risk envelope (relocated from System's PositionRiskTab). stop_loss_pct is a
 * downside %, target_pct_gain an upside % gain, horizon_days the holding window. These are
 * display-only — NOT orders, never sent to any broker (the book is paper-only).
 *
 * #1834 — the current-position marker on that range.
 *
 * UNITS, concluded from this file rather than assumed: `stopLossPct` and `targetPctGain` are
 * PERCENTAGES RELATIVE TO ENTRY (a downside % and an upside % gain), never absolute prices —
 * this component is handed no price and can compute none. So the bar's axis is a percent-vs-
 * entry axis running from `-down` at the left end (the stop) through 0 (entry — the accent
 * tick the file already places at `down / span`) to `+up` at the right end (the target).
 * {@link Valuation.unrealizedPct} is measured in that SAME unit (percent points versus
 * `entry_price`), so it drops straight onto the axis:
 *
 *     fraction = (unrealizedPct + down) / span,   span = down + up
 *
 * which lands on the axis's three fixed points exactly: `-down → 0`, `0 → down/span` (the
 * existing entry tick), `+up → 1`. Feeding it a price, or a change-vs-prior-close, would
 * render a confident wrong marker; the value must be a since-entry percentage.
 *
 * The marker is DISPLAY ONLY and reads a `Valuation` the caller derived — nothing here is
 * persisted, and the close-keyed record is never written (see lib/live-valuation.ts).
 */
export default function RiskEnvelopeCell({
  stopLossPct,
  targetPctGain,
  horizonDays,
  valuation,
}: {
  stopLossPct: number | null | undefined;
  targetPctGain: number | null | undefined;
  horizonDays: number | null | undefined;
  /**
   * Where the position is trading now, in percent points vs entry, with its provenance.
   * Omitted, null, or `source: 'unavailable'` hides the marker — a marker parked at the
   * midpoint is indistinguishable from a real reading and is worse than none.
   *
   * A STALE quote (`source: 'live'`, `isFresh: false`) still gets its marker drawn: it is the
   * best mark available and hiding it would show less than the truth. What changes is the
   * spoken label, which states the quote's age instead of calling it live.
   */
  valuation?: Valuation | null;
}) {
  const hasStop = stopLossPct != null;
  const hasTarget = targetPctGain != null;
  const hasHorizon = horizonDays != null;
  if (!hasStop && !hasTarget && !hasHorizon) {
    return <span className="text-ink-mute">—</span>;
  }
  // Position the entry (0%) tick proportionally between the stop and target ends.
  const down = hasStop ? Math.abs(stopLossPct as number) : 0;
  const up = hasTarget ? Math.abs(targetPctGain as number) : 0;
  const span = down + up;
  const entryPct = span > 0 ? (down / span) * 100 : 50;
  const mark = positionMark(valuation, { down, up, span, hasStop, hasTarget });
  return (
    <div className="flex items-center justify-end gap-2">
      <div className="flex flex-col items-end gap-1">
        <div className="flex items-center gap-2 font-mono text-[11px] tabular-nums">
          <span className={hasStop ? 'text-down' : 'text-ink-mute'}>
            {hasStop
              ? `${(stopLossPct as number) >= 0 ? '+' : ''}${(stopLossPct as number).toFixed(1)}%`
              : '—'}
          </span>
          <span className="text-ink-mute">↔</span>
          <span className={hasTarget ? 'text-up' : 'text-ink-mute'}>
            {hasTarget ? `+${(targetPctGain as number).toFixed(1)}%` : '—'}
          </span>
        </div>
        {(hasStop || hasTarget) && (
          // The track is a picture of the numbers printed directly above it, so it is hidden
          // from assistive tech and the marker's meaning is carried by the sr-only sibling
          // below — not by the tooltip, which only mouse users ever get.
          <div
            className="relative h-1 w-24 bg-term-bg"
            title={mark?.label}
            aria-hidden
          >
            <div className="absolute inset-y-0 left-0 w-1/2 rounded-l-full bg-down/40" />
            <div className="absolute inset-y-0 right-0 w-1/2 rounded-r-full bg-up/40" />
            <div
              className="absolute -top-0.5 h-2 w-0.5 bg-accent"
              style={{ left: `${entryPct}%` }}
              aria-hidden
            />
            {mark && (
              <span
                data-live-mark=""
                data-pin-edge={mark.pinned ?? undefined}
                className={
                  mark.pinned
                    ? // A pinned marker gets its own SHAPE — an outward-pointing caret — so it
                      // cannot be read as "sitting exactly on the boundary", which is the moment
                      // the display matters most. Shape, not colour, carries the distinction.
                      `absolute -top-[3px] h-0 w-0 border-y-[5px] border-y-transparent ${
                        mark.pinned === 'target'
                          ? 'border-l-[7px] border-l-ink'
                          : 'border-r-[7px] border-r-ink'
                      }`
                    : 'absolute -top-1 h-3 w-[3px] bg-ink'
                }
                // Inline because the offset is data-derived. The pinned carets are pulled
                // INSIDE the track (translate -100% / 0) rather than overhanging it, so a
                // clamped marker cannot widen the row inside the table's overflow container.
                style={{ left: `${mark.leftPct}%`, transform: mark.transform }}
                aria-hidden
              />
            )}
          </div>
        )}
        {mark && <span className="sr-only">{mark.label}</span>}
      </div>
      {hasHorizon && (
        <span className="rounded border border-warn/30 bg-warn/10 px-1.5 py-0.5 font-mono text-[10px] tabular-nums text-warn">
          {horizonDays}d
        </span>
      )}
    </div>
  );
}

interface PositionMark {
  /** Clamped to [0, 100] — a reading past an end pins there instead of overflowing the track. */
  leftPct: number;
  /** Which end it is pinned against, or null when the reading is genuinely inside the range. */
  pinned: 'stop' | 'target' | null;
  transform: string;
  /** Announced (sr-only) and offered as the track's tooltip — never colour-only. */
  label: string;
}

/**
 * Where to draw the marker, or null when nothing defensible can be drawn.
 *
 * Hidden — never defaulted to the midpoint — when the valuation is `unavailable`, when it
 * carries no since-entry percentage, or when the envelope has zero width. That last case is
 * the subtle one: `entryPct` falls back to a fabricated 50% when `span` is 0, and a marker at
 * a fabricated centre reads as a real measurement.
 */
function positionMark(
  valuation: Valuation | null | undefined,
  bounds: { down: number; up: number; span: number; hasStop: boolean; hasTarget: boolean }
): PositionMark | null {
  if (!valuation || valuation.source === 'unavailable') return null;
  const now = valuation.unrealizedPct;
  if (now == null || !Number.isFinite(now)) return null;
  const { down, up, span, hasStop, hasTarget } = bounds;
  if (!(span > 0)) return null;

  const raw = (now + down) / span;
  const pinned: 'stop' | 'target' | null = raw < 0 ? 'stop' : raw > 1 ? 'target' : null;
  const leftPct = Math.min(1, Math.max(0, raw)) * 100;
  const signed = `${now >= 0 ? '+' : ''}${now.toFixed(1)}%`;
  // "beyond the target" would be a lie on a half envelope (target unset ⇒ the right end is
  // entry, not a target), so the wording follows what the row actually has.
  const where =
    pinned === 'target'
      ? hasTarget
        ? `beyond the +${up.toFixed(1)}% target`
        : 'above the plotted range'
      : pinned === 'stop'
        ? hasStop
          ? 'through the stop'
          : 'below the plotted range'
        : 'inside the stop-to-target range';
  // THE GATE IS `source === 'live' && isFresh`, both halves. `source` alone would call a quote
  // that stopped advancing 18 hours ago "live"; `isFresh` alone is false on every close too, so
  // it would describe an ordinary close as a stale quote. Neither claim is the other's.
  const age = formatQuoteAge(valuation.ageMs);
  const basis =
    valuation.source !== 'live'
      ? 'at the last close'
      : valuation.isFresh
        ? 'live'
        : age
          ? `on a quote ${age} old`
          : 'on a quote of unknown age';
  return {
    leftPct,
    pinned,
    transform: pinned === 'target' ? 'translateX(-100%)' : pinned ? 'none' : 'translateX(-50%)',
    label: `Now ${signed} vs entry ${basis}, ${where}.`,
  };
}
