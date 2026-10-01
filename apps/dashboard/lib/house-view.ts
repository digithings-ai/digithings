/**
 * Pure derivations for the House surface (Corpus / Book / Profile). No React,
 * no fetching: every function takes already-loaded dashboard data and returns
 * plain view models so the page stays a thin renderer and every null path is
 * testable.
 */
import { ALL_PLAN_TIERS, ARTIFACT_CLASSES, can, type ArtifactClass, type PlanTier } from './entitlements';
import { isSharedCorpusKey } from './house-identity';
import { DEFAULT_SNAPSHOT_STALENESS_HOURS, isStale } from './snapshot-staleness';
import type { DeltaRequestMeta, Doc, NavChartPoint, Position } from './types';

const DAY_MS = 86_400_000;
const CALENDAR_DAYS = 53 * 7;
const ISO_DAY = /^\d{4}-\d{2}-\d{2}/;

export interface LabelCount {
  label: string;
  value: number;
}

export interface CorpusView {
  total: number;
  /** Per-day doc counts inside the calendar window, ascending. */
  days: Array<{ date: string; count: number }>;
  daysCovered: number;
  latestDate: string | null;
  /** Share of docs from delta runs, 0..100; null when no doc carries a run type. */
  deltaSharePct: number | null;
  baselineCount: number;
  deltaCount: number;
  /** Docs whose path/id is a theme:/asset:/segment: key. */
  keyedCount: number;
  keyedPct: number | null;
  /** Weekly doc counts, oldest first, for a sparkline. */
  weekly: number[];
  /** Paths touched by delta requests in the last 7 covered days. */
  changedPaths7d: number;
  byCategory: LabelCount[];
  bySegment: LabelCount[];
  bySector: LabelCount[];
  sampleKeys: string[];
}

function isoDay(value: string | null | undefined): string | null {
  if (!value || !ISO_DAY.test(value)) return null;
  return value.slice(0, 10);
}

function tally(values: Array<string | null | undefined>, top: number): LabelCount[] {
  const counts = new Map<string, number>();
  for (const v of values) {
    const key = (v ?? '').trim();
    if (!key) continue;
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return [...counts.entries()]
    .map(([label, value]) => ({ label, value }))
    .sort((a, b) => b.value - a.value || a.label.localeCompare(b.label))
    .slice(0, top);
}

function shiftDay(iso: string, deltaDays: number): string {
  return new Date(Date.parse(`${iso}T00:00:00Z`) + deltaDays * DAY_MS).toISOString().slice(0, 10);
}

/** Derive corpus health facts from the documents index. `null`-safe for DB-down. */
export function buildCorpusView(
  docs: readonly Doc[] | null | undefined,
  deltaMeta: Record<string, DeltaRequestMeta> | null | undefined = null,
  topN = 6
): CorpusView {
  const list = docs ?? [];
  const perDay = new Map<string, number>();
  let baselineCount = 0;
  let deltaCount = 0;
  let keyedCount = 0;
  const sampleKeys: string[] = [];
  for (const d of list) {
    const day = isoDay(d.date);
    if (day) perDay.set(day, (perDay.get(day) ?? 0) + 1);
    if (d.runType === 'baseline') baselineCount += 1;
    else if (d.runType === 'delta') deltaCount += 1;
    const key = d.path || d.id || '';
    if (key && isSharedCorpusKey(key)) {
      keyedCount += 1;
      if (sampleKeys.length < 12) sampleKeys.push(key);
    }
  }
  const sortedDays = [...perDay.keys()].sort();
  const latestDate = sortedDays.length ? sortedDays[sortedDays.length - 1] : null;

  let days: CorpusView['days'] = [];
  let weekly: number[] = [];
  if (latestDate) {
    const start = shiftDay(latestDate, -(CALENDAR_DAYS - 1));
    for (let i = 0; i < CALENDAR_DAYS; i += 1) {
      const date = shiftDay(start, i);
      days.push({ date, count: perDay.get(date) ?? 0 });
    }
    weekly = [];
    for (let w = 0; w < CALENDAR_DAYS / 7; w += 1) {
      weekly.push(days.slice(w * 7, w * 7 + 7).reduce((s, d) => s + d.count, 0));
    }
  }

  const metaDays = Object.keys(deltaMeta ?? {}).sort().slice(-7);
  const changed = new Set<string>();
  for (const day of metaDays) for (const p of deltaMeta?.[day]?.changed_paths ?? []) changed.add(p);

  const typed = baselineCount + deltaCount;
  return {
    total: list.length,
    days,
    daysCovered: sortedDays.length,
    latestDate,
    deltaSharePct: typed > 0 ? (deltaCount / typed) * 100 : null,
    baselineCount,
    deltaCount,
    keyedCount,
    keyedPct: list.length > 0 ? (keyedCount / list.length) * 100 : null,
    weekly,
    changedPaths7d: changed.size,
    byCategory: tally(list.map((d) => d.category), topN),
    bySegment: tally(list.map((d) => d.segment), topN),
    bySector: tally(list.map((d) => d.sector), topN),
    sampleKeys,
  };
}

export interface RunFreshness {
  /** accent when the last run is within the staleness window, warn otherwise, off when unknown. */
  tone: 'ok' | 'warn' | 'off';
  label: string;
}

/** Health (not P&L) freshness of the always-on run. */
export function houseFreshness(
  lastRunAt: string | null | undefined,
  now: Date = new Date(),
  hours: number = DEFAULT_SNAPSHOT_STALENESS_HOURS
): RunFreshness {
  if (!lastRunAt || Number.isNaN(Date.parse(lastRunAt))) return { tone: 'off', label: 'No run recorded' };
  return isStale(lastRunAt, hours, now)
    ? { tone: 'warn', label: `Stale: last run ${lastRunAt.slice(0, 10)}` }
    : { tone: 'ok', label: `Fresh: last run ${lastRunAt.slice(0, 10)}` };
}

export interface BookView {
  positionCount: number;
  longCount: number;
  shortCount: number;
  grossPct: number;
  cashPct: number | null;
  /** Sleeve weights (by category, else ticker), largest first. */
  sleeves: Array<{ id: string; label: string; value: number }>;
  /** Largest positions for a treemap. */
  holdings: Array<{ id: string; label: string; value: number; detail: string }>;
  /** Positions whose actual weight drifted from target by more than `driftPp`. */
  drifted: number;
  nav: number[];
  navReturnPct: number | null;
  latestNav: number | null;
}

/** Derive book composition + NAV trend. Null-safe for DB-down. */
export function buildBookView(
  positions: readonly Position[] | null | undefined,
  snapshots: readonly NavChartPoint[] | null | undefined,
  cashPct: number | null | undefined = null,
  driftPp = 1
): BookView {
  const list = (positions ?? []).filter((p) => Number.isFinite(p.weight_actual));
  const sleeveMap = new Map<string, number>();
  let gross = 0;
  let drifted = 0;
  for (const p of list) {
    const w = Math.abs(p.weight_actual);
    gross += w;
    const key = (p.category ?? '').trim() || 'Uncategorised';
    sleeveMap.set(key, (sleeveMap.get(key) ?? 0) + w);
    if (typeof p.weight_target === 'number' && Math.abs(p.weight_actual - p.weight_target) > driftPp) drifted += 1;
  }
  const sleeves = [...sleeveMap.entries()]
    .map(([label, value]) => ({ id: label, label, value }))
    .sort((a, b) => b.value - a.value);
  const holdings = list
    .filter((p) => Math.abs(p.weight_actual) > 0)
    .map((p) => ({
      id: p.ticker,
      label: p.ticker,
      value: Math.abs(p.weight_actual),
      detail: `${p.type === 'SHORT' ? 'S' : 'L'} ${Math.abs(p.weight_actual).toFixed(1)}%`,
    }))
    .sort((a, b) => b.value - a.value)
    .slice(0, 24);

  const nav = (snapshots ?? [])
    .map((s) => s.nav)
    .filter((n): n is number => typeof n === 'number' && Number.isFinite(n));
  const first = nav[0];
  const last = nav[nav.length - 1];
  return {
    positionCount: list.length,
    longCount: list.filter((p) => p.type === 'LONG').length,
    shortCount: list.filter((p) => p.type === 'SHORT').length,
    grossPct: gross,
    cashPct: typeof cashPct === 'number' && Number.isFinite(cashPct) ? cashPct : null,
    sleeves,
    holdings,
    drifted,
    nav,
    navReturnPct: nav.length >= 2 && first !== 0 ? ((last - first) / first) * 100 : null,
    latestNav: nav.length ? last : null,
  };
}

export interface ProfileView {
  /** Categories observed in the book: the declared universe as actually held. */
  universe: string[];
  /** Scalar constraints only, key-sorted. */
  constraints: Array<{ key: string; value: string }>;
  tiers: readonly PlanTier[];
  classes: readonly ArtifactClass[];
  /** `grid[tierIndex][classIndex]` is 1 when the tier may see the class, else 0. */
  grid: number[][];
}

export function buildProfileView(
  positions: readonly Position[] | null | undefined,
  constraints: Record<string, unknown> | null | undefined
): ProfileView {
  const universe = [
    ...new Set((positions ?? []).map((p) => (p.category ?? '').trim()).filter(Boolean)),
  ].sort();
  const rows = Object.entries(constraints ?? {})
    .filter(([, v]) => ['string', 'number', 'boolean'].includes(typeof v))
    .map(([key, v]) => ({ key, value: String(v) }))
    .sort((a, b) => a.key.localeCompare(b.key));
  return {
    universe,
    constraints: rows,
    tiers: ALL_PLAN_TIERS,
    classes: ARTIFACT_CLASSES,
    grid: ALL_PLAN_TIERS.map((t) => ARTIFACT_CLASSES.map((c) => (can(t, c) ? 1 : 0))),
  };
}
