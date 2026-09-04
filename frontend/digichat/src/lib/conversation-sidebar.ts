/** Pure helpers for the authenticated conversation sidebar (#205). */

export type SidebarThread = {
  id: string;
  title: string;
  updatedAt: string;
};

export type SidebarDateGroup = {
  label: "Today" | "Yesterday" | "Last 7 days" | "Older";
  items: SidebarThread[];
};

/** Case-insensitive title match; empty/whitespace query returns all threads. */
export function filterThreadsByQuery<T extends SidebarThread>(
  threads: T[],
  query: string,
): T[] {
  const q = query.trim().toLowerCase();
  if (!q) return threads;
  return threads.filter((t) => t.title.toLowerCase().includes(q));
}

/**
 * Bucket threads by last activity. Callers should pass threads already sorted
 * by `updatedAt` desc (as `mergeRemoteAndLocal` does).
 */
export function groupThreadsByDate(
  threads: SidebarThread[],
  now: Date = new Date(),
): SidebarDateGroup[] {
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const yesterdayStart = todayStart - 24 * 60 * 60 * 1000;
  const weekStart = todayStart - 7 * 24 * 60 * 60 * 1000;
  const buckets: Record<SidebarDateGroup["label"], SidebarThread[]> = {
    Today: [],
    Yesterday: [],
    "Last 7 days": [],
    Older: [],
  };
  for (const t of threads) {
    const ts = Date.parse(t.updatedAt);
    if (Number.isNaN(ts) || ts >= todayStart) buckets.Today.push(t);
    else if (ts >= yesterdayStart) buckets.Yesterday.push(t);
    else if (ts >= weekStart) buckets["Last 7 days"].push(t);
    else buckets.Older.push(t);
  }
  return (Object.keys(buckets) as SidebarDateGroup["label"][])
    .filter((label) => buckets[label].length > 0)
    .map((label) => ({ label, items: buckets[label] }));
}
