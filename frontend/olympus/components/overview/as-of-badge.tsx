'use client';

import { Badge } from '@/components/ui';

/**
 * Glanceable freshness pill for the regime hero. Amber when the run date is
 * older than yesterday (UTC) — the same "today or yesterday is fresh" window
 * the snapshot fetch uses — so the owner can tell at a glance whether the
 * morning read reflects a current run. Self-contained: derives staleness from
 * the date alone (no envelope timestamp needed).
 */
export function AsOfBadge({ date, now }: { date: string | null; now?: Date }) {
  if (!date) return null;
  const ref = now ?? new Date();
  const yesterday = new Date(ref);
  yesterday.setUTCDate(yesterday.getUTCDate() - 1);
  const yIso = yesterday.toISOString().slice(0, 10);
  const stale = date < yIso;

  const label = `as of ${formatAsOf(date)}`;
  if (stale) {
    return (
      <Badge variant="amber" className="font-mono">
        {label} · stale
      </Badge>
    );
  }
  return (
    <span className="font-mono text-[10px] text-text-muted tracking-wide">{label}</span>
  );
}

/** "2026-06-13" → "Jun 13". Falls back to the raw string on a parse miss. */
function formatAsOf(date: string): string {
  const m = date.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!m) return date;
  const months = [
    'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
  ];
  const mi = Number(m[2]) - 1;
  if (mi < 0 || mi > 11) return date;
  return `${months[mi]} ${Number(m[3])}`;
}
