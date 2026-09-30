import { RangeTrack } from '@digithings/ui/ui';
import { formatHoldPct } from '@/lib/twelve-x/trade-history';

/**
 * Observed excursion range for one idea, drawn in the Impact column.
 *
 * `maxAdverse` / `maxFavorable` are the worst/best direction-signed
 * excursions seen while the idea was live (fractions vs entry, scored from
 * daily closes); the ink marker is the hold return, also scored from daily
 * closes. All three share one
 * axis running from the low extreme through 0 (entry — the accent tick) to
 * the high extreme. Display-only: renders the stored excursion and close
 * marks; level touches are scored upstream.
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
  const label =
    hold === null
      ? `Observed extremes ${formatHoldPct(adv)} to ${formatHoldPct(fav)} vs entry, no close mark.`
      : `Observed extremes ${formatHoldPct(adv)} to ${formatHoldPct(fav)} vs entry, close mark ${formatHoldPct(hold)}.`;
  return (
    <span className="inline-flex flex-col items-end gap-1">
      <span className="font-mono text-[11px] tabular-nums text-ink-soft">
        {formatHoldPct(adv)}
        <span className="text-ink-mute"> ↔ </span>
        {formatHoldPct(fav)}
      </span>
      <RangeTrack
        className="w-24"
        low={lo}
        high={hi}
        envelope
        label="Excursion vs entry"
        format={formatHoldPct}
        markers={[
          { kind: 'entry', value: 0, label: 'Entry' },
          ...(hold === null ? [] : [{ kind: 'current' as const, value: hold, label: 'Close mark' }]),
        ]}
      />
      <span className="sr-only">{label}</span>
    </span>
  );
}
