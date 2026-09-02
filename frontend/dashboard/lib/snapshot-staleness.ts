/**
 * Snapshot staleness checks.
 *
 * The published-at timestamp on a `SnapshotEnvelope` is UTC. The frontend
 * shows a "stale" banner when the freshest envelope was assembled more than
 * `hours` ago. The default of 48h matches the Atlas weekly-baseline +
 * weekday-delta cadence: a missing weekday delta should still be shown,
 * but anything older than two days warrants a visible warning.
 */

/** ISO date / datetime string accepted by `Date.parse`. */
export type IsoTimestamp = string;

/**
 * Returns true when `publishedAt` was more than `hours` ago vs `now`.
 * Returns true (treated as "definitely stale") when the input cannot be parsed —
 * the UI fails loud rather than silently rendering stale content.
 */
export function isStale(
  publishedAt: IsoTimestamp,
  hours: number,
  now: Date = new Date(),
): boolean {
  if (!publishedAt) return true;
  const ts = Date.parse(publishedAt);
  if (Number.isNaN(ts)) return true;
  const ageMs = now.getTime() - ts;
  if (ageMs < 0) return false;
  return ageMs > hours * 60 * 60 * 1000;
}

/** Default staleness threshold (hours) for the Atlas daily snapshot UI. */
export const DEFAULT_SNAPSHOT_STALENESS_HOURS = 48;

/**
 * Human-readable age in the form "Xh ago" / "Xd ago" suitable for the
 * stale banner subtitle. Returns `null` when `publishedAt` cannot be parsed.
 */
export function formatAge(publishedAt: IsoTimestamp, now: Date = new Date()): string | null {
  if (!publishedAt) return null;
  const ts = Date.parse(publishedAt);
  if (Number.isNaN(ts)) return null;
  const minutes = Math.max(0, Math.floor((now.getTime() - ts) / 60_000));
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}
