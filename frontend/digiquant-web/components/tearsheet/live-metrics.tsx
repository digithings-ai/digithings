/** Nightly tearsheet pipeline stamps ``generated_at`` when backtests refresh. */

import { LiveBadge } from "@digithings/web";

/** Green pulse + “live” when backtest metrics are present — the family
 *  LiveBadge (#1463); whether it shows at all is this app's data wiring. */
export function LiveMetricsBadge({
  generatedAt,
  className,
}: {
  generatedAt: string | null | undefined;
  className?: string;
}) {
  if (!generatedAt) return null;
  return <LiveBadge ariaLabel="Live backtest metrics" className={className} />;
}
