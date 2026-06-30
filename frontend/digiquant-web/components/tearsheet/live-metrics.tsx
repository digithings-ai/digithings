/** Nightly tearsheet pipeline stamps ``generated_at`` when backtests refresh. */

/** Green pulse + “live” when backtest metrics are present. */
export function LiveMetricsBadge({
  generatedAt,
  className = "",
}: {
  generatedAt: string | null | undefined;
  className?: string;
}) {
  if (!generatedAt) return null;

  return (
    <span
      className={`ts-live-badge${className ? ` ${className}` : ""}`}
      aria-label="Live backtest metrics"
    >
      <span className="ts-live-dot" aria-hidden="true" />
      <span className="ts-live-label">live</span>
    </span>
  );
}
