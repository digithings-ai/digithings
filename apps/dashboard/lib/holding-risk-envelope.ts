/**
 * Advisory risk-envelope geometry for one holding (display only, never an order).
 *
 * The axis is PERCENT VERSUS ENTRY, `-|stop| .. +|target|`, with entry at 0.
 * `Valuation.unrealizedPct` is measured in that same unit, so a live or close
 * reading drops straight onto it. Feeding a price or a change-vs-prior-close
 * would draw a confident wrong marker; the value must be a since-entry percent.
 *
 * The marker is hidden (never defaulted to the midpoint) when the valuation is
 * unavailable, carries no since-entry percentage, or the envelope has zero
 * width. The spoken label states its basis: "live" only when `source === 'live'`
 * AND the quote is fresh; a stale quote states its age; a close says so.
 */
import { envelopeRange, type RangeMarker } from '@digithings/ui/ui';
import { formatQuoteAge, type Valuation } from './live-valuation';

export interface RiskEnvelopeView {
  hasStop: boolean;
  hasTarget: boolean;
  /** Axis ends for `RangeTrack` (percent vs entry). */
  low: number;
  high: number;
  /** entry + stop + target + (when drawable) the current reading. */
  markers: RangeMarker[];
  /** The current reading, or null when nothing defensible can be drawn. */
  mark: {
    /** Which end it is pinned against, or null when genuinely inside the range. */
    pinned: 'stop' | 'target' | null;
    /** Announced (sr-only) and offered as the tooltip, never colour-only. */
    label: string;
  } | null;
}

export function riskEnvelopeView(
  stopLossPct: number | null | undefined,
  targetPctGain: number | null | undefined,
  valuation?: Valuation | null
): RiskEnvelopeView {
  const hasStop = stopLossPct != null;
  const hasTarget = targetPctGain != null;
  const { low, high } = envelopeRange(stopLossPct, targetPctGain);
  const span = high - low;

  const markers: RangeMarker[] = [{ kind: 'entry', value: 0, label: 'Entry' }];
  if (hasStop) markers.push({ kind: 'stop', value: low, label: 'Stop' });
  if (hasTarget) markers.push({ kind: 'target', value: high, label: 'Target' });

  let mark: RiskEnvelopeView['mark'] = null;
  const now = valuation && valuation.source !== 'unavailable' ? valuation.unrealizedPct : null;
  if (valuation && now != null && Number.isFinite(now) && span > 0) {
    const raw = (now - low) / span;
    const pinned: 'stop' | 'target' | null = raw < 0 ? 'stop' : raw > 1 ? 'target' : null;
    const signed = `${now >= 0 ? '+' : ''}${now.toFixed(1)}%`;
    // "beyond the target" would be a lie on a half envelope (target unset means the right end
    // is entry, not a target), so the wording follows what the row actually has.
    const where =
      pinned === 'target'
        ? hasTarget
          ? `beyond the +${high.toFixed(1)}% target`
          : 'above the plotted range'
        : pinned === 'stop'
          ? hasStop
            ? 'through the stop'
            : 'below the plotted range'
          : 'inside the stop-to-target range';
    const age = formatQuoteAge(valuation.ageMs);
    const basis =
      valuation.source !== 'live'
        ? 'at the last close'
        : valuation.isFresh
          ? 'live'
          : age
            ? `on a quote ${age} old`
            : 'on a quote of unknown age';
    mark = { pinned, label: `Now ${signed} vs entry ${basis}, ${where}.` };
    markers.push({ kind: 'current', value: now, label: 'Now' });
  }

  return { hasStop, hasTarget, low, high, markers, mark };
}
