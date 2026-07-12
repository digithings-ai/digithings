'use client';

import { Badge } from '@/components/ui';
import { isStale, formatAge, DEFAULT_SNAPSHOT_STALENESS_HOURS } from '@/lib/snapshot-staleness';

/**
 * F7 — the single freshness component. Two presentations from one source:
 * Settings/System render the labelled Status block; Today renders a glanceable
 * inline pill. When `createdAt` (daily_snapshots.created_at, UTC) is supplied we
 * use the true-age `isStale`/`formatAge` path; otherwise we fall back to the
 * date-only "today or yesterday is fresh" window the snapshot fetch uses.
 */
export function AsOfBadge({
  date,
  createdAt,
  now,
  staleHours = DEFAULT_SNAPSHOT_STALENESS_HOURS,
}: {
  date: string | null;
  createdAt?: string | null;
  now?: Date;
  staleHours?: number;
}) {
  if (!date) return null;
  const ref = now ?? new Date();

  let stale: boolean;
  let agePart = '';
  if (createdAt) {
    stale = isStale(createdAt, staleHours, ref);
    const age = formatAge(createdAt, ref);
    agePart = age ? ` · ${age}` : '';
  } else {
    const yesterday = new Date(ref);
    yesterday.setUTCDate(yesterday.getUTCDate() - 1);
    stale = date < yesterday.toISOString().slice(0, 10);
  }

  const label = `as of ${formatAsOf(date)}${agePart}`;
  if (stale) {
    // Reference badge dress is already mono — the old `font-mono` utility
    // is redundant.
    return <Badge variant="amber">{label} · stale</Badge>;
  }
  return <span className="font-mono text-[10px] text-ink-mute tracking-wide">{label}</span>;
}

/** "2026-06-13" → "Jun 13". Falls back to the raw string on a parse miss. */
function formatAsOf(date: string): string {
  const m = date.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!m) return date;
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const mi = Number(m[2]) - 1;
  if (mi < 0 || mi > 11) return date;
  return `${months[mi]} ${Number(m[3])}`;
}
