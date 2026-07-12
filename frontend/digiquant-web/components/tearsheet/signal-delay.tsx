/** Published strategies run live on a deliberate N-day signal delay — a
 *  marketing feature: the live book trails the public backtest so the model
 *  can't be front-run off the tearsheet (#1462). Rendered as the family
 *  `ts-chip` pill; the full sentence rides `title` + `aria-label` on every
 *  instance so the delay is explained regardless of the visible copy.
 *  Absent / 0 days => no chip (back-compat with pre-1.2 sheets). */

export function SignalDelayChip({
  days,
  detail = "concise",
  className,
}: {
  days: number | null | undefined;
  /** "concise" for cards, "full" for the standalone tearsheet header. */
  detail?: "concise" | "full";
  className?: string;
}) {
  if (!days || days <= 0) return null;
  const unit = days === 1 ? "day" : "days";
  const full = `Backtested strategy running live — signals delayed ${days} ${unit} to protect the model`;
  const label = detail === "full" ? full : `Signals +${days}d delayed`;
  return (
    <span
      className={"ts-chip" + (className ? ` ${className}` : "")}
      title={full}
      aria-label={full}
    >
      {label}
    </span>
  );
}
