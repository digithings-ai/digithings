import { formatHoldPct } from '@/lib/twelve-x/trade-history';

/**
 * Observed excursion range for one idea, drawn in the Impact column.
 *
 * `maxAdverse` / `maxFavorable` are the worst/best direction-signed
 * excursions seen while the idea was live (fractions vs entry, scored from
 * daily closes); the ink marker is the hold return, also scored from daily
 * closes. All three share one
 * axis running from the low extreme through 0 (entry — the accent tick) to
 * the high extreme. Display-only: levels never drive lifecycle scoring.
 */
export default function ExcursionRangeCell({
  maxAdverse,
  maxFavorable,
  holdReturn,
}: {
  maxAdverse: number | null | undefined;
  maxFavorable: number | null | undefined;
  holdReturn: number | null | undefined;
}) {
  const adv = Number.isFinite(maxAdverse) ? (maxAdverse as number) : null;
  const fav = Number.isFinite(maxFavorable) ? (maxFavorable as number) : null;
  const hold = Number.isFinite(holdReturn) ? (holdReturn as number) : null;
  if (adv === null && fav === null) {
    return <span className="text-ink-mute">—</span>;
  }
  const lo = Math.min(adv ?? 0, hold ?? 0, 0);
  const hi = Math.max(fav ?? 0, hold ?? 0, 0);
  if (!(hi - lo > 0)) {
    return <span className="text-ink-mute">—</span>;
  }
  const toPct = (v: number) => ((v - lo) / (hi - lo)) * 100;
  const entryLeft = toPct(0);
  const holdLeft = hold === null ? null : toPct(Math.min(hi, Math.max(lo, hold)));
  const label =
    hold === null
      ? `Observed extremes ${formatHoldPct(adv)} to ${formatHoldPct(fav)} vs entry, no close mark.`
      : `Observed extremes ${formatHoldPct(adv)} to ${formatHoldPct(fav)} vs entry, close mark ${formatHoldPct(hold)}.`;
  return (
    <span className="inline-flex flex-col items-end gap-1">
      <span className="font-mono text-[11px] tabular-nums">
        <span className="text-down">{formatHoldPct(adv)}</span>
        <span className="text-ink-mute"> ↔ </span>
        <span className="text-up">{formatHoldPct(fav)}</span>
      </span>
      {/* The track pictures the numbers above it: hidden from assistive tech,
          meaning conveyed by the sr-only label — never colour-only, no tooltip. */}
      <span className="relative h-1 w-24 bg-term-bg" aria-hidden>
        <span
          className="absolute inset-y-0 rounded-l-full bg-down/40"
          style={{ left: `${toPct(lo)}%`, width: `${entryLeft - toPct(lo)}%` }}
          aria-hidden
        />
        <span
          className="absolute inset-y-0 rounded-r-full bg-up/40"
          style={{ left: `${entryLeft}%`, width: `${toPct(hi) - entryLeft}%` }}
          aria-hidden
        />
        <span
          className="absolute -top-0.5 h-2 w-0.5 bg-accent"
          style={{ left: `${entryLeft}%` }}
          aria-hidden
        />
        {holdLeft !== null && (
          <span
            className="absolute -top-1 h-3 w-[3px] bg-ink"
            style={{ left: `${holdLeft}%`, transform: 'translateX(-50%)' }}
            aria-hidden
          />
        )}
      </span>
      <span className="sr-only">{label}</span>
    </span>
  );
}
