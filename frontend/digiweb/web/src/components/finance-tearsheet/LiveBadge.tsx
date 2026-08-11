/**
 * LiveBadge (#1463) — the pulsing-dot live indicator promoted from
 * frontend/digiquant-web/components/tearsheet/live-metrics.tsx. The accent
 * dot pulse (`@keyframes ts-live-pulse`) lives in
 * styles/finance-tearsheet.css; in print the badge is hidden (live-ness is
 * meaningless on paper). Whether the badge shows at all (e.g. only when a
 * nightly pipeline stamped `generated_at`) is consumer data wiring. Server
 * component — no state, no effects.
 */

export interface LiveBadgeProps {
  /** Badge copy — lowercase by grammar (the dress lowercases regardless). */
  label?: string;
  /** AT description; the pulse itself is decorative. */
  ariaLabel?: string;
  className?: string;
}

export function LiveBadge({ label = "live", ariaLabel = "Live metrics", className }: LiveBadgeProps) {
  return (
    <span
      className={"ts-live-badge" + (className ? ` ${className}` : "")}
      aria-label={ariaLabel}
    >
      <span className="ts-live-dot" aria-hidden="true" />
      <span className="ts-live-label">{label}</span>
    </span>
  );
}
