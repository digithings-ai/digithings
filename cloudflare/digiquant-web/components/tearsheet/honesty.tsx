/**
 * Public-honesty chips for remaining-book / DCA tearsheets.
 * Full-sample Nautilus vs-flat is not walk-forward OOS; do not badge a win.
 */

export function BacktestOnlyChip({ className }: { className?: string }) {
  return (
    <span
      className={"ts-chip ts-chip-soft" + (className ? ` ${className}` : "")}
      title="Illustrative Nautilus backtest — not a live trading strategy"
      aria-label="Backtest only"
    >
      Backtest only
    </span>
  );
}

export function OosHonestyChip({
  beatsFlatDcaOos,
}: {
  beatsFlatDcaOos: boolean | null | undefined;
}) {
  if (beatsFlatDcaOos === true) return null;
  return (
    <span
      className="ts-chip ts-chip-soft"
      title="Walk-forward out-of-sample vs flat DCA does not beat. Full-sample vs-flat is the backtest window, not OOS."
      aria-label="Does not beat flat DCA out of sample"
    >
      Not OOS vs flat DCA
    </span>
  );
}
