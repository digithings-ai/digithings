import { Badge } from "@digithings/web/ui";

/**
 * Public-honesty chips for remaining-book / DCA tearsheets.
 * Full-sample Nautilus vs-flat is not walk-forward OOS; do not badge a win.
 */

export function BacktestOnlyChip({ className }: { className?: string }) {
  return (
    <Badge
      variant="outline"
      className={"text-ink-soft" + (className ? ` ${className}` : "")}
      title="Illustrative Nautilus backtest — not a live trading strategy"
      aria-label="Backtest only"
    >
      Backtest only
    </Badge>
  );
}

export function OosHonestyChip({
  beatsFlatDcaOos,
}: {
  beatsFlatDcaOos: boolean | null | undefined;
}) {
  if (beatsFlatDcaOos === true) return null;
  return (
    <Badge
      variant="outline"
      className="text-ink-soft"
      title="Walk-forward out-of-sample vs flat DCA does not beat. Full-sample vs-flat is the backtest window, not OOS."
      aria-label="Does not beat flat DCA out of sample"
    >
      Not OOS vs flat DCA
    </Badge>
  );
}
