import type { RepoPullItem } from "./types";

export type HeatDay = { date: string; count: number };

const DAY_MS = 86_400_000;

/** `2026-08-21T17:35:10Z` → `2026-08-21`; empty string when absent. */
function dayOf(stamp: string | null | undefined): string {
  return stamp ? stamp.slice(0, 10) : "";
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
  const add = (stamp: string | null | undefined) => {
    const day = dayOf(stamp);
    if (!day) return;
    const ms = Date.parse(`${day}T00:00:00Z`);
    if (Number.isNaN(ms) || ms < startMs || ms > endMs) return;
    counts.set(day, (counts.get(day) ?? 0) + 1);
  };
  for (const p of pulls) add(p.mergedAt);
  for (const c of commits) add(c);
  for (const i of closedIssues) add(i);
  const days: HeatDay[] = [];
  for (let i = 0; i < total; i++) {
    const date = isoOf(startMs + i * DAY_MS);
    days.push({ date, count: counts.get(date) ?? 0 });
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
