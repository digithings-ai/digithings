'use client';

import { RangeTrack } from '@digithings/ui/ui';
import type { Valuation } from '@/lib/live-valuation';
import { riskEnvelopeView } from '@/lib/holding-risk-envelope';

/**
 * Advisory risk envelope: stop_loss_pct is a downside %, target_pct_gain an upside %
 * gain, horizon_days the holding window. Display-only, NOT orders, never sent to any
 * broker (the book is paper-only).
 *
 * A thin adapter over the kit `RangeTrack`: the axis is percent-vs-entry
 * (`-|stop| .. +|target|`), entry is the accent tick at 0, stop and target are LEVELS
 * (warn / accent), not P&L, and the current reading (#1834) pins to an end with a caret
 * shape rather than overflowing. Geometry and the spoken basis live in
 * `lib/holding-risk-envelope.ts`. The marker is DISPLAY ONLY and reads a `Valuation` the
 * caller derived, so nothing here is persisted (see lib/live-valuation.ts).
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
   * Omitted, null, or `source: 'unavailable'` hides the marker. A STALE quote still gets
   * its marker drawn (best mark available); only the spoken label states its age.
   */
  valuation?: Valuation | null;
}) {
  const hasHorizon = horizonDays != null;
  const view = riskEnvelopeView(stopLossPct, targetPctGain, valuation);
  if (!view.hasStop && !view.hasTarget && !hasHorizon) {
    return <span className="text-ink-mute">—</span>;
  }
  return (
    <div className="flex items-center justify-end gap-2">
      <div className="flex w-28 flex-col items-end gap-1">
        <div className="flex items-center gap-2 font-mono text-[11px] tabular-nums">
          <span className={view.hasStop ? 'text-warn' : 'text-ink-mute'}>
            {view.hasStop
              ? `${(stopLossPct as number) >= 0 ? '+' : ''}${(stopLossPct as number).toFixed(1)}%`
              : '—'}
          </span>
          <span className="text-ink-mute">↔</span>
          <span className={view.hasTarget ? 'text-accent' : 'text-ink-mute'}>
            {view.hasTarget ? `+${(targetPctGain as number).toFixed(1)}%` : '—'}
          </span>
        </div>
        {view.hasStop || view.hasTarget ? (
          // The track pictures the numbers printed above it; the marker's meaning is carried
          // by the sr-only sibling, not the tooltip only mouse users get.
          <div className="w-full" aria-hidden title={view.mark?.label}>
            <RangeTrack
              low={view.low}
              high={view.high}
              markers={view.markers}
              envelope
              label="Stop to target"
              data-live-mark={view.mark ? '' : undefined}
              data-pin-edge={view.mark?.pinned ?? undefined}
            />
          </div>
        ) : null}
        {view.mark ? <span className="sr-only">{view.mark.label}</span> : null}
      </div>
      {hasHorizon ? (
        <span className="rounded border border-warn/30 bg-warn/10 px-1.5 py-0.5 font-mono text-[10px] tabular-nums text-warn">
          {horizonDays}d
        </span>
      ) : null}
    </div>
  );
}
