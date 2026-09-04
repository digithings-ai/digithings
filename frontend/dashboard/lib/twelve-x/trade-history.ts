/**
 * Pure assembly for the Trades history table: full idea rows joined to
 * lifecycle eval rows. Close-based verdicts only — excursion (bias) and
 * level-touch verdicts arrive with the high/low feed + eval migration.
 */
import type { FxIdeaEvalRow, FxLevelProvenance, FxTradeIdeaRow } from './types';
import { formatLevelValue, hasTradeLevels, parseTradeLevels } from './trade-levels';

export type TradeLifecycle = 'live' | 'closed' | 'no_data' | 'unscored';

/** Displayable result labels — no-data / unscored rows are dropped before render. */
export type TradeResult = 'right' | 'wrong' | 'live';

export interface TradeHistoryRow {
  runDate: string;
  rank: number;
  pair: string;
  direction: string;
  title: string;
  catalyst: string;
  entryBand: string | null;
  stop: string | null;
  target: string | null;
  hasLevels: boolean;
  lifecycle: TradeLifecycle;
  entryDate: string | null;
  exitDate: string | null;
  sessions: number | null;
  /** Signed trade-direction hold return (fraction, e.g. 0.012 = +1.2%). */
  holdReturn: number | null;
  directionalWin: boolean | null;
}

export type ResultFilter = 'all' | 'wins' | 'losses' | 'live';

export interface TradeHistoryFilters {
  result: ResultFilter;
  /** Exact pair match, or 'all'. */
  pair: string;
  /**
   * Inclusive board-date range (YYYY-MM-DD). `null` means unbound on that side.
   * Both null → all boards.
   */
  boardFrom: string | null;
  boardTo: string | null;
  /**
   * Minimum absolute Impact (hold return) to keep.
   * 0.001 = 0.1%. Rows without a finite hold return fail this gate when > 0.
   */
  minAbsImpact: number;
}

export type TradeSortKey =
  | 'generated'
  | 'pair'
  | 'bias'
  | 'entry'
  | 'stop'
  | 'target'
  | 'active'
  | 'impact'
  | 'result';

export type SortDir = 'asc' | 'desc';

export interface TradeHistorySummary {
  /** Rights / (rights + wrongs) among filtered resolved rows; null when none resolved. */
  pctRight: number | null;
  rightCount: number;
  wrongCount: number;
  liveCount: number;
  resolvedCount: number;
  /** Mean signed hold return among rights with finite Impact. */
  avgReturnRights: number | null;
  /** Mean signed hold return among wrongs with finite Impact (typically ≤ 0). */
  avgReturnWrongs: number | null;
}

function evalKey(runDate: string, rank: number): string {
  return `${runDate}::${rank}`;
}

function lifecycleOf(status: string | undefined): TradeLifecycle {
  if (!status) return 'unscored';
  if (status === 'open') return 'live';
  if (status === 'missing_rates') return 'no_data';
  return 'closed';
}

/** Signed hold return as a one-decimal percent, or an em dash when unknown. */
export function formatHoldPct(holdReturn: number | null | undefined): string {
  if (holdReturn === null || holdReturn === undefined || !Number.isFinite(holdReturn)) {
    return '—';
  }
  const pct = holdReturn * 100;
  const sign = pct > 0 ? '+' : '';
  return `${sign}${pct.toFixed(1)}%`;
}

/** Format a 0–1 fraction as a whole percent string, or em dash. */
export function formatPctRight(pct: number | null | undefined): string {
  if (pct === null || pct === undefined || !Number.isFinite(pct)) return '—';
  return `${(pct * 100).toFixed(0)}%`;
}

export function biasLabel(direction: string): string {
  const d = direction.trim().toLowerCase();
  if (d === 'long') return 'Long';
  if (d === 'short') return 'Short';
  return direction;
}

/**
 * Map a joined history row to Right / Wrong / Live, or null when it must be
 * discarded (no_data, unscored, closed without a directional verdict).
 */
export function tradeResult(row: TradeHistoryRow): TradeResult | null {
  if (row.lifecycle === 'no_data' || row.lifecycle === 'unscored') return null;
  if (row.lifecycle === 'live') return 'live';
  if (row.directionalWin === true) return 'right';
  if (row.directionalWin === false) return 'wrong';
  return null;
}

/** Drop rows that cannot show Right / Wrong / Live. */
export function displayableTradeHistory(rows: TradeHistoryRow[]): TradeHistoryRow[] {
  return rows.filter((r) => tradeResult(r) !== null);
}

export function assembleTradeHistory(
  ideas: FxTradeIdeaRow[],
  ideaEval: FxIdeaEvalRow[],
): TradeHistoryRow[] {
  const evalByKey = new Map(ideaEval.map((r) => [evalKey(r.run_date, r.rank), r]));
  return ideas
    .map((idea) => {
      const ev = evalByKey.get(evalKey(idea.run_date, idea.rank));
      const tl = parseTradeLevels(idea.trade_levels);
      const fmt = (value: string, provenance?: FxLevelProvenance) =>
        formatLevelValue(value, idea.pair, provenance);
      const entryBand =
        tl?.entry_low && tl?.entry_high
          ? `${fmt(tl.entry_low.value, tl.entry_low.provenance)}–${fmt(tl.entry_high.value, tl.entry_high.provenance)}`
          : (tl?.entry_low ?? tl?.entry_high)
            ? fmt(
                (tl.entry_low ?? tl.entry_high)?.value ?? '',
                (tl.entry_low ?? tl.entry_high)?.provenance,
              )
            : null;
      return {
        runDate: idea.run_date,
        rank: idea.rank,
        pair: idea.pair,
        direction: idea.direction,
        title: idea.title,
        catalyst: idea.catalyst,
        entryBand,
        stop: tl?.stop ? fmt(tl.stop.value, tl.stop.provenance) : null,
        target: tl && tl.targets.length > 0 ? fmt(tl.targets[0].value, tl.targets[0].provenance) : null,
        hasLevels: hasTradeLevels(tl),
        lifecycle: lifecycleOf(ev?.status),
        entryDate: ev?.entry_date ?? null,
        exitDate: ev?.exit_date ?? null,
        sessions: ev?.n_sessions ?? null,
        holdReturn: ev?.hold_return ?? ev?.ret ?? null,
        directionalWin: ev?.directional_win ?? ev?.hit ?? null,
      } satisfies TradeHistoryRow;
    })
    .sort((a, b) => b.runDate.localeCompare(a.runDate) || a.rank - b.rank);
}

/** True when `runDate` falls in inclusive `[from, to]` (null = unbound). */
export function boardDateInRange(
  runDate: string,
  from: string | null,
  to: string | null,
): boolean {
  if (from !== null && runDate < from) return false;
  if (to !== null && runDate > to) return false;
  return true;
}

export function filterTradeHistory(
  rows: TradeHistoryRow[],
  filters: TradeHistoryFilters,
): TradeHistoryRow[] {
  return rows.filter((row) => {
    const result = tradeResult(row);
    if (result === null) return false;

    if (filters.result === 'wins' && result !== 'right') return false;
    if (filters.result === 'losses' && result !== 'wrong') return false;
    if (filters.result === 'live' && result !== 'live') return false;

    if (filters.pair !== 'all' && row.pair !== filters.pair) return false;
    if (!boardDateInRange(row.runDate, filters.boardFrom, filters.boardTo)) return false;

    if (filters.minAbsImpact > 0) {
      if (row.holdReturn === null || !Number.isFinite(row.holdReturn)) return false;
      if (Math.abs(row.holdReturn) < filters.minAbsImpact) return false;
    }

    return true;
  });
}

function mean(values: number[]): number | null {
  if (values.length === 0) return null;
  return values.reduce((a, b) => a + b, 0) / values.length;
}

/** Summary metrics always computed from the filtered row set. */
export function summarizeFilteredTrades(rows: TradeHistoryRow[]): TradeHistorySummary {
  let rightCount = 0;
  let wrongCount = 0;
  let liveCount = 0;
  const rightReturns: number[] = [];
  const wrongReturns: number[] = [];

  for (const row of rows) {
    const result = tradeResult(row);
    if (result === 'live') {
      liveCount += 1;
      continue;
    }
    if (result === 'right') {
      rightCount += 1;
      if (row.holdReturn !== null && Number.isFinite(row.holdReturn)) {
        rightReturns.push(row.holdReturn);
      }
      continue;
    }
    if (result === 'wrong') {
      wrongCount += 1;
      if (row.holdReturn !== null && Number.isFinite(row.holdReturn)) {
        wrongReturns.push(row.holdReturn);
      }
    }
  }

  const resolvedCount = rightCount + wrongCount;
  return {
    pctRight: resolvedCount === 0 ? null : rightCount / resolvedCount,
    rightCount,
    wrongCount,
    liveCount,
    resolvedCount,
    avgReturnRights: mean(rightReturns),
    avgReturnWrongs: mean(wrongReturns),
  };
}

function cmpNullableNumber(a: number | null, b: number | null, mul: number): number {
  if (a === null && b === null) return 0;
  if (a === null) return 1;
  if (b === null) return -1;
  return mul * (a - b);
}

/** First finite number in a formatted level string (handles bands like `148.2–148.6`). */
export function levelSortKey(value: string | null): number | null {
  if (value === null) return null;
  const match = value.match(/-?\d+(?:\.\d+)?/);
  if (!match) return null;
  const n = Number(match[0]);
  return Number.isFinite(n) ? n : null;
}

const RESULT_ORDER: Record<TradeResult, number> = { right: 0, wrong: 1, live: 2 };

export function sortTradeHistory(
  rows: TradeHistoryRow[],
  sortKey: TradeSortKey | null,
  sortDir: SortDir,
): TradeHistoryRow[] {
  if (sortKey === null) return rows;
  const mul = sortDir === 'asc' ? 1 : -1;
  return [...rows].sort((a, b) => {
    switch (sortKey) {
      case 'generated':
        return mul * a.runDate.localeCompare(b.runDate) || mul * (a.rank - b.rank);
      case 'pair':
        return mul * a.pair.localeCompare(b.pair);
      case 'bias':
        return mul * biasLabel(a.direction).localeCompare(biasLabel(b.direction));
      case 'entry':
        return cmpNullableNumber(levelSortKey(a.entryBand), levelSortKey(b.entryBand), mul);
      case 'stop':
        return cmpNullableNumber(levelSortKey(a.stop), levelSortKey(b.stop), mul);
      case 'target':
        return cmpNullableNumber(levelSortKey(a.target), levelSortKey(b.target), mul);
      case 'active':
        return cmpNullableNumber(a.sessions, b.sessions, mul);
      case 'impact':
        return cmpNullableNumber(a.holdReturn, b.holdReturn, mul);
      case 'result': {
        const ar = tradeResult(a);
        const br = tradeResult(b);
        if (ar === null && br === null) return 0;
        if (ar === null) return 1;
        if (br === null) return -1;
        return mul * (RESULT_ORDER[ar] - RESULT_ORDER[br]);
      }
      default:
        return 0;
    }
  });
}

export function uniquePairs(rows: TradeHistoryRow[]): string[] {
  return [...new Set(rows.map((r) => r.pair))].sort((a, b) => a.localeCompare(b));
}

export function uniqueBoards(rows: TradeHistoryRow[]): string[] {
  return [...new Set(rows.map((r) => r.runDate))].sort((a, b) => b.localeCompare(a));
}
