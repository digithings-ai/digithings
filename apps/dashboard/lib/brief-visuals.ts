/**
 * Pure data-derivation for the Brief visuals (sparklines, hero NAV chart,
 * composition bar, movers, rebalance bullets, run-segment strip). No React, no
 * fetching — everything here is unit-tested in `brief-visuals.test.ts`.
 *
 * Honesty rules: series come from the persisted `/performance` NAV points only
 * (the live-marks overlay never leaks into a chart); a series that cannot be
 * drawn honestly (too short, no benchmark overlap) is returned as `[]` so the
 * caller renders an em-dash / "not enough history" state instead of a stub.
 */
import { MIN_OVERLAP_DAYS } from '@digithings/ui';
import type { ReconciledPosition } from '@/lib/book-reconciliation';
import type { RebalanceAction } from '@/lib/types';

export interface BriefNavPoint {
  date: string;
  /** Base-100 index from `/performance`. */
  index: number;
  day_return_pct?: number | null;
}

export interface BenchmarkPricePoint {
  date: string;
  price: number;
}

export type BriefRange = '1M' | '3M' | 'ALL';
export const BRIEF_RANGES: readonly BriefRange[] = ['1M', '3M', 'ALL'];

/** Fewest points for which a line is meaningful. */
export const MIN_SERIES_POINTS = 2;

const RANGE_DAYS: Record<Exclude<BriefRange, 'ALL'>, number> = { '1M': 31, '3M': 92 };

function isNum(v: unknown): v is number {
  return typeof v === 'number' && Number.isFinite(v);
}

/** Clean, date-ascending, finite-only NAV points. */
export function cleanNavPoints(points: readonly BriefNavPoint[] | null | undefined): BriefNavPoint[] {
  return (points ?? [])
    .filter((p) => p && typeof p.date === 'string' && isNum(p.index))
    .slice()
    .sort((a, b) => a.date.localeCompare(b.date));
}

/** Trailing window ending at the last point (calendar-day cutoff). */
export function windowNavPoints(
  points: readonly BriefNavPoint[] | null | undefined,
  range: BriefRange
): BriefNavPoint[] {
  const clean = cleanNavPoints(points);
  if (range === 'ALL' || clean.length === 0) return clean;
  const tip = Date.parse(`${clean[clean.length - 1].date}T00:00:00Z`);
  if (!Number.isFinite(tip)) return clean;
  const cutoff = tip - RANGE_DAYS[range] * 86_400_000;
  return clean.filter((p) => {
    const t = Date.parse(`${p.date}T00:00:00Z`);
    return Number.isFinite(t) && t >= cutoff;
  });
}

/** Last `n` values (kept in order); `[]` when fewer than 2 points exist. */
export function sparkValues(values: readonly number[], n: number): number[] {
  if (values.length < MIN_SERIES_POINTS) return [];
  return values.slice(-Math.max(MIN_SERIES_POINTS, n));
}

export function navSparkValues(
  points: readonly BriefNavPoint[] | null | undefined,
  n: number
): number[] {
  return sparkValues(cleanNavPoints(points).map((p) => p.index), n);
}

/**
 * Relative return of the portfolio vs a benchmark, in percent, on the dates the
 * two series share, rebased to the first shared date. Fails closed (`[]`) below
 * the kit's minimum overlap so a thin alignment never draws a confident line.
 */
/**
 * Clip NAV points to the current source run (#3767 / #3935). The headline
 * since-inception/excess is rebased on the current run's start date, so any
 * excess series must start there too — never span a legacy→finalized seam.
 * A missing/invalid start returns the points unchanged.
 */
export function clipToRun(
  points: readonly BriefNavPoint[] | null | undefined,
  runStartDate: string | null | undefined
): BriefNavPoint[] {
  const clean = cleanNavPoints(points);
  if (!runStartDate) return clean;
  const clipped = clean.filter((p) => p.date >= runStartDate);
  return clipped.length > 0 ? clipped : clean;
}

export function excessSeries(
  points: readonly BriefNavPoint[] | null | undefined,
  bench: readonly BenchmarkPricePoint[] | null | undefined,
  minOverlap: number = MIN_OVERLAP_DAYS
): number[] {
  if (!bench || bench.length === 0) return [];
  const byDate = new Map<string, number>();
  for (const b of bench) {
    if (isNum(b.price) && b.price > 0) byDate.set(b.date, b.price);
  }
  const shared = cleanNavPoints(points)
    .filter((p) => p.index > 0 && byDate.has(p.date))
    .map((p) => ({ nav: p.index, bench: byDate.get(p.date) as number }));
  if (shared.length < Math.max(minOverlap, MIN_SERIES_POINTS)) return [];
  const { nav: nav0, bench: bench0 } = shared[0];
  return shared.map((s) => (s.nav / nav0 / (s.bench / bench0) - 1) * 100);
}

export interface SeriesStats {
  first: number;
  last: number;
  /** last/first - 1, in percent. */
  changePct: number;
  high: number;
  low: number;
  /** Deepest peak-to-trough fall as a non-positive percent. */
  maxDrawdownPct: number;
}

export function seriesStats(values: readonly number[]): SeriesStats | null {
  const v = values.filter(isNum);
  if (v.length < MIN_SERIES_POINTS || v[0] === 0) return null;
  let peak = v[0];
  let dd = 0;
  for (const x of v) {
    if (x > peak) peak = x;
    if (peak > 0) dd = Math.min(dd, (x / peak - 1) * 100);
  }
  return {
    first: v[0],
    last: v[v.length - 1],
    changePct: (v[v.length - 1] / v[0] - 1) * 100,
    high: Math.max(...v),
    low: Math.min(...v),
    maxDrawdownPct: dd,
  };
}

/** P&L tone for a series: direction of last vs first; flat/unknown is neutral. */
export function trendTone(values: readonly number[]): 'up' | 'down' | 'ink' {
  const v = values.filter(isNum);
  if (v.length < MIN_SERIES_POINTS) return 'ink';
  const d = v[v.length - 1] - v[0];
  return d > 0 ? 'up' : d < 0 ? 'down' : 'ink';
}

// ─── Composition ─────────────────────────────────────────────────────────────

export interface BriefCompositionSegment {
  key: string;
  label: string;
  value: number;
  cash?: boolean;
}

/**
 * Held names by normalized weight (largest first, top `maxNamed`), the tail
 * folded into "Other", then a cash segment for the undeployed remainder.
 */
export function compositionSegments(
  held: readonly ReconciledPosition[],
  cashPct: number,
  maxNamed = 8
): BriefCompositionSegment[] {
  const ranked = held
    .filter((p) => isNum(p.normalizedWeight) && p.normalizedWeight > 0)
    .slice()
    .sort((a, b) => b.normalizedWeight - a.normalizedWeight);
  const named = ranked.slice(0, maxNamed);
  const rest = ranked.slice(maxNamed);
  const out: BriefCompositionSegment[] = named.map((p) => ({
    key: p.ticker,
    label: p.ticker,
    value: p.normalizedWeight,
  }));
  const other = rest.reduce((a, p) => a + p.normalizedWeight, 0);
  if (other > 0) out.push({ key: 'other', label: `Other (${rest.length})`, value: other });
  if (isNum(cashPct) && cashPct > 0) {
    out.push({ key: 'cash', label: 'Cash', value: cashPct, cash: true });
  }
  return out;
}

// ─── Movers ──────────────────────────────────────────────────────────────────

export interface MoverItem {
  id: string;
  label: string;
  value: number | null;
  display: string;
}

export function signedPctText(value: number | null | undefined, digits = 1): string {
  if (!isNum(value)) return '—';
  return `${value > 0 ? '+' : ''}${value.toFixed(digits)}%`;
}

/** Top `n` held names by |day change|; names with no day change are dropped. */
export function moverItems(held: readonly ReconciledPosition[], n = 6): MoverItem[] {
  return held
    .filter((p) => isNum(p.day_change_pct))
    .slice()
    .sort((a, b) => Math.abs(b.day_change_pct ?? 0) - Math.abs(a.day_change_pct ?? 0))
    .slice(0, n)
    .map((p) => ({
      id: p.ticker,
      label: p.ticker,
      value: p.day_change_pct ?? null,
      display: signedPctText(p.day_change_pct),
    }));
}

// ─── Rebalance bullets ───────────────────────────────────────────────────────

export interface RebalanceBullet {
  ticker: string;
  verb: string;
  current: number;
  recommended: number;
  /** Allocation direction is not P&L: accent = adding, warn = reducing. */
  tone: 'accent' | 'warn' | 'mute';
  /** Shared axis maximum so bars across rows are comparable. */
  axisMax: number;
  text: string;
}

export function rebalanceBullets(actions: readonly RebalanceAction[]): RebalanceBullet[] {
  const rows = actions.filter(
    (a) => isNum(a.current_pct) && isNum(a.recommended_pct) && a.current_pct !== a.recommended_pct
  );
  const axisMax = Math.max(1, ...rows.map((a) => Math.max(a.current_pct, a.recommended_pct))) * 1.15;
  return rows.map((a) => {
    const ticker = a.ticker.trim().toUpperCase();
    const verb = a.action ? a.action.charAt(0).toUpperCase() + a.action.slice(1).toLowerCase() : 'Change';
    const delta = a.recommended_pct - a.current_pct;
    return {
      ticker,
      verb,
      current: a.current_pct,
      recommended: a.recommended_pct,
      tone: delta > 0 ? 'accent' : delta < 0 ? 'warn' : 'mute',
      axisMax,
      text: `${a.current_pct.toFixed(1)}% → ${a.recommended_pct.toFixed(1)}%`,
    };
  });
}

// ─── Run health ──────────────────────────────────────────────────────────────

export interface RunSegmentInput {
  segmentsOk: number | null;
  segmentsTotal: number | null;
  segmentsCarried: number | null;
  segmentsFailed: number | null;
}

export interface RunSegmentCell {
  key: string;
  tone: 'ok' | 'warn' | 'off' | 'idle';
  label: string;
}

const MAX_SEGMENT_CELLS = 48;

/**
 * One cell per pipeline segment. Health tones only: ok = accent, carried from a
 * prior run = mute, failed = warn, unaccounted = hollow. `[]` when the total is
 * unknown so the caller shows nothing rather than a fabricated strip.
 */
export function runSegmentCells(run: RunSegmentInput | null | undefined): RunSegmentCell[] {
  const total = run?.segmentsTotal;
  if (!run || !isNum(total) || total <= 0) return [];
  const cap = Math.min(Math.floor(total), MAX_SEGMENT_CELLS);
  const failed = Math.max(0, run.segmentsFailed ?? 0);
  const carried = Math.max(0, run.segmentsCarried ?? 0);
  const ok = Math.max(0, run.segmentsOk ?? 0);
  const cells: RunSegmentCell[] = [];
  const push = (n: number, tone: RunSegmentCell['tone'], label: string) => {
    for (let i = 0; i < n && cells.length < cap; i++) {
      cells.push({ key: `${tone}-${cells.length}`, tone, label });
    }
  };
  push(ok, 'ok', 'Segment ok');
  push(carried, 'off', 'Segment carried from a prior run');
  push(failed, 'warn', 'Segment failed');
  push(cap - cells.length, 'idle', 'Segment not reported');
  return cells;
}

// ─── Thesis / ledger tones ───────────────────────────────────────────────────

export function thesisStatusTone(status: string | null | undefined): 'ok' | 'warn' | 'off' {
  const s = (status ?? '').toLowerCase();
  if (s.includes('confirmed') || s.includes('active')) return 'ok';
  if (s.includes('monitor') || s.includes('watch') || s.includes('invalid') || s.includes('broken')) {
    return 'warn';
  }
  return 'off';
}

export function ledgerEventTone(event: string): 'ok' | 'warn' | 'off' {
  const e = event.toUpperCase();
  if (e === 'OPEN' || e === 'ADD') return 'ok';
  if (e === 'TRIM' || e === 'EXIT') return 'warn';
  return 'off';
}
