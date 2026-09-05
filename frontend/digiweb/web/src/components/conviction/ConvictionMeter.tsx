/**
 * ConvictionMeter — the single canonical UNSIGNED conviction encoding,
 * promoted from `frontend/dashboard/components/shared/conviction-meter.tsx`
 * (dashboard F6 ruling, preserved verbatim): integer pips (max 3 for
 * `positions.conviction`, max 4 for pre-scaled `theses.confidence`), filled
 * pips `--accent`, empty pips `--hair`, accent the only color on its row
 * (F5). Value is clamped and rounded; the redundant `aria-label` + `sr-only`
 * pair and `data-filled` attributes are preserved for testability.
 *
 * Utility-classed (no family CSS); consuming apps need an `@source` line
 * for this directory (MIGRATION.md rule 3).
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
            data-filled={isFilled ? "true" : "false"}
            className={`h-1.5 w-1.5 rounded-full ${
              isFilled ? "bg-accent" : "bg-hair"
            }`}
          />
        );
      })}
      <span className="sr-only">{srLabel}</span>
    </span>
  );
}
