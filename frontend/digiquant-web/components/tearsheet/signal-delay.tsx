/** Published strategies run live on a deliberate N-day signal delay so the
 *  model can't be front-run off the tearsheet (#1462). Rendered as the family
 *  `ts-chip` pill with simple copy ("Signals delayed 3 days" / "Signals +3d
 *  delayed"); a short tooltip rides `title` + `aria-label`.
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
  const label = detail === "full" ? `Signals delayed ${days} ${unit}` : `Signals +${days}d delayed`;
  const tip = `Live signals are delayed ${days} ${unit}`;
  return (
    <span
      className={"ts-chip" + (className ? ` ${className}` : "")}
      title={tip}
      aria-label={tip}
    >
      {label}
    </span>
  );
}
