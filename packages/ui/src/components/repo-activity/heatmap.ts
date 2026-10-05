import type { RepoPullItem } from "./types";

/**
 * One UTC day of contribution history. `count` is the total; the three source
 * fields are the split behind it, present only when the caller bucketed them
 * (`bucketContributions`). The heat cell's `title` reads the split so hovering a
 * square says where the day's work came from, not just how much there was.
 */
export type HeatDay = {
  date: string;
  count: number;
  pulls?: number;
  commits?: number;
  issues?: number;
};

const DAY_MS = 86_400_000;

/** Stamp → UTC calendar day (`2026-08-21T00:30:00+02:00` → `2026-08-20`); "" when absent. */
function dayOf(stamp: string | null | undefined): string {
  if (!stamp) return "";
  const ms = Date.parse(stamp);
  return Number.isNaN(ms) ? "" : isoOf(ms);
}

function toUtcMidnight(d: Date): number {
  return Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate());
}

function isoOf(ms: number): string {
  return new Date(ms).toISOString().slice(0, 10);
}

/**
 * Bucket merged-PR merge dates into consecutive UTC days, oldest → newest.
 * `weeks * 7` cells ending at `end` (default today). Pulls outside the window
 * or without a date are ignored. Pure — safe for SSR and tests.
 */
export function bucketDaily(
  pulls: RepoPullItem[],
  weeks = 16,
  end: Date = new Date(),
): HeatDay[] {
  const safeWeeks = Math.max(1, Math.floor(weeks));
  const endMs = toUtcMidnight(end);
  const total = safeWeeks * 7;
  const startMs = endMs - (total - 1) * DAY_MS;
  const counts = new Map<string, number>();
  for (const p of pulls) {
    const day = dayOf(p.mergedAt);
    if (!day) continue;
    const ms = Date.parse(`${day}T00:00:00Z`);
    if (Number.isNaN(ms) || ms < startMs || ms > endMs) continue;
    counts.set(day, (counts.get(day) ?? 0) + 1);
  }
  const days: HeatDay[] = [];
  for (let i = 0; i < total; i++) {
    const date = isoOf(startMs + i * DAY_MS);
    days.push({ date, count: counts.get(date) ?? 0 });
  }
  return days;
}

/**
 * Bucket repo-level contributions (GitHub profile-graph style) into
 * consecutive UTC days, oldest → newest. Sums merged PRs + commits +
 * closed issues per day so the heat tracks contributions, not merges alone.
 * Each source is an ISO timestamp (or null); undated or out-of-window
 * entries are ignored. Pure — safe for SSR and tests.
 */
export function bucketContributions(
  pulls: RepoPullItem[],
  commits: Array<string | null | undefined> = [],
  closedIssues: Array<string | null | undefined> = [],
  weeks = 53,
  end: Date = new Date(),
): HeatDay[] {
  const safeWeeks = Math.max(1, Math.floor(weeks));
  const endMs = toUtcMidnight(end);
  const total = safeWeeks * 7;
  const startMs = endMs - (total - 1) * DAY_MS;
  const counts = new Map<string, number>();
  const split = {
    pulls: new Map<string, number>(),
    commits: new Map<string, number>(),
    issues: new Map<string, number>(),
  };
  const bump = (bucket: Map<string, number>, day: string) =>
    bucket.set(day, (bucket.get(day) ?? 0) + 1);
  const add = (bucket: Map<string, number>, stamp: string | null | undefined) => {
    const day = dayOf(stamp);
    if (!day) return;
    const ms = Date.parse(`${day}T00:00:00Z`);
    if (Number.isNaN(ms) || ms < startMs || ms > endMs) return;
    counts.set(day, (counts.get(day) ?? 0) + 1);
    bump(bucket, day);
  };
  for (const p of pulls) add(split.pulls, p.mergedAt);
  for (const c of commits) add(split.commits, c);
  for (const i of closedIssues) add(split.issues, i);
  const days: HeatDay[] = [];
  for (let i = 0; i < total; i++) {
    const date = isoOf(startMs + i * DAY_MS);
    days.push({
      date,
      count: counts.get(date) ?? 0,
      pulls: split.pulls.get(date) ?? 0,
      commits: split.commits.get(date) ?? 0,
      issues: split.issues.get(date) ?? 0,
    });
  }
  return days;
}

/**
 * Accent step for a cell: 0 when empty, otherwise 1–4. Small maxima map
 * 1:1; larger ones use quartiles so a single busy day cannot flatten the rest.
 */
export function levelFor(count: number, max: number): 0 | 1 | 2 | 3 | 4 {
  if (count <= 0) return 0;
  if (max <= 4) return Math.min(4, count) as 1 | 2 | 3 | 4;
  return Math.min(4, Math.max(1, Math.ceil((count / max) * 4))) as 1 | 2 | 3 | 4;
}
