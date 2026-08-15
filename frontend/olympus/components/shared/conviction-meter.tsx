/**
 * F6 — the single canonical UNSIGNED conviction encoding: a cyan pip/dot meter.
 * Used for `positions.conviction` (1–3 integer pips, max=3) and pre-scaled
 * `theses.confidence`. Cyan `--accent` is the ONLY color here (F5): filled pips
 * are accent, empty pips are border-subtle. Must be the only accent on its row.
 */
export function ConvictionMeter({
  value,
  max = 3,
  srLabel,
}: {
  value: number;
  max?: number;
  srLabel: string;
}) {
  const filled = Math.max(0, Math.min(max, Math.round(value)));
  return (
    <span className="inline-flex items-center gap-1" role="img" aria-label={srLabel}>
      {Array.from({ length: max }).map((_, i) => {
        const isFilled = i < filled;
        return (
          <span
            key={i}
            data-filled={isFilled ? 'true' : 'false'}
            className={`h-1.5 w-1.5 rounded-full ${
              isFilled ? 'bg-accent' : 'bg-hair'
            }`}
          />
        );
      })}
      <span className="sr-only">{srLabel}</span>
    </span>
  );
}
