/** Nightly tearsheet pipeline stamps ``generated_at`` when backtests refresh. */

export function formatMetricsUpdatedAt(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  try {
    return new Intl.DateTimeFormat("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
      timeZone: "UTC",
      timeZoneName: "short",
    }).format(d);
  } catch {
    return `${d.toISOString().slice(0, 16).replace("T", " ")} UTC`;
  }
}

export function liveMetricsTooltip(iso: string): string {
  return `Backtest refreshed ${formatMetricsUpdatedAt(iso)}`;
}

/** Green pulse + “live” — hover/focus shows last ``generated_at``. */
export function LiveMetricsBadge({
  generatedAt,
  className = "",
}: {
  generatedAt: string | null | undefined;
  className?: string;
}) {
  if (!generatedAt) return null;

  const tip = liveMetricsTooltip(generatedAt);

  return (
    <span
      className={`ts-live-badge${className ? ` ${className}` : ""}`}
      tabIndex={0}
      aria-label={tip}
    >
      <span className="ts-live-dot" aria-hidden="true" />
      <span className="ts-live-label">live</span>
      <span className="ts-live-tip" role="tooltip">
        {tip}
      </span>
    </span>
  );
}
