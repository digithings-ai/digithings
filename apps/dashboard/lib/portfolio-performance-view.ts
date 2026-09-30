/**
 * Pure derivation for the Performance view (NAV vs benchmark, drawdown,
 * contribution ranking, the current-book lookback bridge). No React, no I/O:
 * every figure the charts draw is computed here so it can be tested and so the
 * sr-only chart summaries quote the same numbers the marks encode.
 */
import type { ContributionReturnPoint } from '@digithings/ui';
import type { TableRow } from '@/lib/database.types';
import type { PerformanceHoldingRow } from '@/components/tearsheet/types';

export type PerformanceRange = '1m' | '3m' | 'ytd' | '1y' | 'all';

export const PERFORMANCE_RANGES: ReadonlyArray<{ value: PerformanceRange; label: string }> = [
  { value: '1m', label: '1M' },
  { value: '3m', label: '3M' },
  { value: 'ytd', label: 'YTD' },
  { value: '1y', label: '1Y' },
  { value: 'all', label: 'All' },
];

export interface DatedReturn {
  date: string;
  returnPct: number;
}

function isNum(v: unknown): v is number {
  return typeof v === 'number' && Number.isFinite(v);
}

/** Start (inclusive) of a lookback window ending at `tip`, or null for `all`. */
export function rangeStart(range: PerformanceRange, tip: string): string | null {
  if (range === 'all') return null;
  if (range === 'ytd') return `${tip.slice(0, 4)}-01-01`;
  const d = new Date(`${tip}T00:00:00Z`);
  if (Number.isNaN(d.getTime())) return null;
  const monthsBack = range === '1m' ? 1 : range === '3m' ? 3 : 12;
  const day = d.getUTCDate();
  d.setUTCDate(1);
  d.setUTCMonth(d.getUTCMonth() - monthsBack);
  const last = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 0)).getUTCDate();
  d.setUTCDate(Math.min(day, last));
  return d.toISOString().slice(0, 10);
}

/** Re-base a cumulative-return series so its first point reads 0%. */
export function rebaseReturns(points: readonly DatedReturn[]): DatedReturn[] {
  const clean = points.filter((p) => p.date && isNum(p.returnPct));
  if (clean.length === 0) return [];
  const base = 1 + clean[0].returnPct / 100;
  if (!(base > 0)) return clean.map((p) => ({ ...p }));
  return clean.map((p) => ({
    date: p.date,
    returnPct: ((1 + p.returnPct / 100) / base - 1) * 100,
  }));
}

/** Window `points` to `range` (ending at the series tip) and re-base to 0% at the window start. */
export function windowReturns(points: readonly DatedReturn[], range: PerformanceRange): DatedReturn[] {
  const sorted = points
    .filter((p) => p.date && isNum(p.returnPct))
    .slice()
    .sort((a, b) => a.date.localeCompare(b.date));
  if (sorted.length === 0) return [];
  const start = rangeStart(range, sorted[sorted.length - 1].date);
  const inWindow = start ? sorted.filter((p) => p.date >= start) : sorted;
  return rebaseReturns(inWindow);
}

/**
 * Benchmark series aligned to the portfolio window: clipped to the same dates
 * and re-based to 0% at the first shared date, so the two lines start together.
 */
export function alignedBenchmark(
  window: readonly DatedReturn[],
  benchmark: readonly DatedReturn[]
): DatedReturn[] {
  if (window.length === 0) return [];
  const first = window[0].date;
  const last = window[window.length - 1].date;
  return rebaseReturns(
    benchmark
      .filter((p) => p.date >= first && p.date <= last)
      .slice()
      .sort((a, b) => a.date.localeCompare(b.date))
  );
}

/** Cumulative excess (portfolio minus benchmark, percentage points) on shared dates. */
export function excessReturns(
  portfolio: readonly DatedReturn[],
  benchmark: readonly DatedReturn[]
): DatedReturn[] {
  const bench = new Map(benchmark.map((p) => [p.date, p.returnPct]));
  return portfolio
    .filter((p) => bench.has(p.date))
    .map((p) => ({ date: p.date, returnPct: p.returnPct - (bench.get(p.date) as number) }));
}

export interface DrawdownStats {
  series: DatedReturn[];
  /** Deepest trough as a negative percent; 0 when the line never fell. */
  maxDrawdownPct: number;
  troughDate: string | null;
  /** Current distance below the running peak (<= 0). */
  currentPct: number;
}

/** Underwater curve from cumulative returns (peak-to-date drawdown, percent, <= 0). */
export function drawdownFromReturns(points: readonly DatedReturn[]): DrawdownStats {
  let peak = -Infinity;
  let maxDd = 0;
  let trough: string | null = null;
  let current = 0;
  const series = points
    .filter((p) => isNum(p.returnPct))
    .map((p) => {
      const level = 1 + p.returnPct / 100;
      if (level > peak) peak = level;
      const dd = peak > 0 ? (level / peak - 1) * 100 : 0;
      if (dd < maxDd) {
        maxDd = dd;
        trough = p.date;
      }
      current = dd;
      return { date: p.date, returnPct: dd };
    });
  return { series, maxDrawdownPct: maxDd, troughDate: trough, currentPct: current };
}

export interface RankedBar {
  id: string;
  label: string;
  value: number;
}

/** Last cumulative per-position contribution (percentage points), ranked by magnitude. */
export function rankedContributions(
  points: readonly ContributionReturnPoint[],
  n = 12
): { bars: RankedBar[]; asOf: string | null; total: number | null } {
  if (points.length === 0) return { bars: [], asOf: null, total: null };
  const last = points[points.length - 1];
  const bars = Object.entries(last.contributions)
    .filter(([, v]) => isNum(v))
    .map(([ticker, v]) => ({ id: ticker, label: ticker, value: v }))
    .sort((a, b) => Math.abs(b.value) - Math.abs(a.value))
    .slice(0, n);
  return { bars, asOf: last.t, total: isNum(last.returnPct) ? last.returnPct : null };
}

/** Ranked bars for open-book unrealized returns (rows without a return are dropped, never zeroed). */
export function unrealizedBars(rows: readonly PerformanceHoldingRow[], n = 12): RankedBar[] {
  return rows
    .filter((r) => isNum(r.unrealizedReturnPct))
    .map((r) => ({ id: r.eventId ?? r.ticker, label: r.ticker, value: r.unrealizedReturnPct as number }))
    .sort((a, b) => Math.abs(b.value) - Math.abs(a.value))
    .slice(0, n);
}

/** Ranked bars for realized exits/trims. The row's date rides in the label so repeated tickers stay distinct. */
export function realizedBars(rows: readonly PerformanceHoldingRow[], n = 12): RankedBar[] {
  return rows
    .filter((r) => isNum(r.realizedReturnPct))
    .map((r, i) => ({
      id: r.eventId ?? `${r.ticker}-${r.attributionDate ?? i}`,
      label: `${r.ticker}${r.disposition ? ` ${r.disposition.toLowerCase()}` : ''}`,
      value: r.realizedReturnPct as number,
    }))
    .sort((a, b) => Math.abs(b.value) - Math.abs(a.value))
    .slice(0, n);
}

type AttributionRow = TableRow<'position_attribution'>;

export interface AttributionBridge {
  benchmarkPct: number;
  selectionPct: number;
  allocationPct: number;
  /** Portion of active return neither selection nor allocation explains (null rows, rounding). */
  residualPct: number;
  activePct: number;
  portfolioPct: number;
}

export interface BookAttributionView {
  holdings: number;
  /** Holdings with no priced window: the totals under-count and the bridge is partial. */
  unpriced: number;
  /** `null` when no row carries the benchmark return (the bridge cannot be anchored). */
  bridge: AttributionBridge | null;
  activePct: number;
  contributors: RankedBar[];
  selectors: RankedBar[];
}

function sum(values: Array<number | null | undefined>): number {
  return values.reduce<number>((acc, v) => acc + (isNum(v) ? v : 0), 0);
}

const isCash = (r: AttributionRow) => r.ticker.trim().toUpperCase() === 'CASH';

/**
 * Brinson-lite bridge for the latest current-book lookback: benchmark, plus
 * selection (weight x excess vs benchmark), plus the cash allocation effect,
 * equals the portfolio's lookback return. This is a LOOKBACK DIAGNOSTIC of
 * today's weights over a trailing window, not realized period P&L.
 */
export function buildBookAttribution(
  rows: readonly AttributionRow[],
  n = 12
): BookAttributionView | null {
  if (rows.length === 0) return null;
  const holdings = rows.filter((r) => !isCash(r));
  const activePct = sum(rows.map((r) => r.total_attribution_pct));
  const newestFirst = [...rows].sort((a, b) => (b.date ?? '').localeCompare(a.date ?? ''));
  const benchmark = newestFirst.find((r) => isNum(r.benchmark_return_pct))?.benchmark_return_pct ?? null;
  const selectionPct = sum(holdings.map((r) => r.selection_effect_pct));
  const allocationPct = sum(rows.map((r) => r.allocation_effect_pct));
  const bridge: AttributionBridge | null = isNum(benchmark)
    ? {
        benchmarkPct: benchmark,
        selectionPct,
        allocationPct,
        residualPct: activePct - selectionPct - allocationPct,
        activePct,
        portfolioPct: benchmark + activePct,
      }
    : null;
  const bars = (pick: (r: AttributionRow) => number | null | undefined): RankedBar[] =>
    holdings
      .filter((r) => isNum(pick(r)))
      .map((r) => ({ id: r.id ?? r.ticker, label: r.ticker, value: pick(r) as number }))
      .sort((a, b) => Math.abs(b.value) - Math.abs(a.value))
      .slice(0, n);
  return {
    holdings: holdings.length,
    unpriced: holdings.filter((r) => r.total_attribution_pct == null).length,
    bridge,
    activePct,
    contributors: bars((r) => r.contribution_pct),
    selectors: bars((r) => r.selection_effect_pct),
  };
}

export interface BridgeStep {
  label: string;
  value: number;
  kind: 'delta' | 'total';
}

/** Steps for WaterfallBridge; the residual step appears only when it is material. */
export function bridgeSteps(bridge: AttributionBridge): BridgeStep[] {
  const steps: BridgeStep[] = [
    { label: 'Benchmark', value: bridge.benchmarkPct, kind: 'total' },
    { label: 'Selection', value: bridge.selectionPct, kind: 'delta' },
    { label: 'Cash alloc.', value: bridge.allocationPct, kind: 'delta' },
  ];
  if (Math.abs(bridge.residualPct) >= 0.005) {
    steps.push({ label: 'Residual', value: bridge.residualPct, kind: 'delta' });
  }
  steps.push({ label: 'Portfolio', value: bridge.portfolioPct, kind: 'total' });
  return steps;
}

/** Signed percent text with an explicit sign and an em dash for null. */
export function signedPct(value: number | null | undefined, digits = 2): string {
  if (!isNum(value)) return '—';
  return `${value > 0 ? '+' : ''}${value.toFixed(digits)}%`;
}

/** One-sentence plain-language chart summary for the NAV-vs-benchmark pane. */
export function navSummary(
  portfolio: readonly DatedReturn[],
  benchmark: readonly DatedReturn[],
  benchmarkLabel: string | null
): string {
  if (portfolio.length < 2) return 'Not enough persisted NAV points to draw a line.';
  const first = portfolio[0].date;
  const last = portfolio[portfolio.length - 1];
  const parts = [`Portfolio ${signedPct(last.returnPct)} from ${first} to ${last.date}`];
  if (benchmarkLabel && benchmark.length > 1) {
    parts.push(`${benchmarkLabel} ${signedPct(benchmark[benchmark.length - 1].returnPct)}`);
  }
  return `${parts.join(', ')}.`;
}
