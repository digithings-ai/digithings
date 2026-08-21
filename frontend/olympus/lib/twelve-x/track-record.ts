/**
 * Pure aggregations for the Track record tab from eval table rows.
 */
import { wilsonInterval, type WilsonInterval } from './wilson';
import type { FxConsensusEvalRow, FxIdeaEvalRow } from './types';

export interface IdeaOutcomeSummary {
  interval: WilsonInterval;
  longInterval: WilsonInterval;
  shortInterval: WilsonInterval;
  targetCount: number;
  stopCount: number;
  replacedCount: number;
  replacedWinCount: number;
  openCount: number;
  missingCount: number;
  significantCount: number;
}

function resolvedWin(row: FxIdeaEvalRow): boolean | null {
  if (row.status === 'hit_target') return true;
  if (row.status === 'hit_stop') return false;
  if (row.status !== 'replaced') return null;
  if (row.directional_win !== null && row.directional_win !== undefined) {
    return row.directional_win;
  }
  return row.hold_return != null ? row.hold_return > 0 : null;
}

function countResolved(
  rows: FxIdeaEvalRow[],
  direction?: string,
): { k: number; n: number } {
  let k = 0;
  let n = 0;
  for (const r of rows) {
    if (direction && r.direction.toLowerCase() !== direction) continue;
    const flag = resolvedWin(r);
    if (flag === null) continue;
    n += 1;
    if (flag) k += 1;
  }
  return { k, n };
}

export function summarizeIdeaOutcomes(rows: FxIdeaEvalRow[]): IdeaOutcomeSummary {
  const all = countResolved(rows);
  const longs = countResolved(rows, 'long');
  const shorts = countResolved(rows, 'short');
  const replaced = rows.filter((r) => r.status === 'replaced');
  return {
    interval: wilsonInterval(all.k, all.n),
    longInterval: wilsonInterval(longs.k, longs.n),
    shortInterval: wilsonInterval(shorts.k, shorts.n),
    targetCount: rows.filter((r) => r.status === 'hit_target').length,
    stopCount: rows.filter((r) => r.status === 'hit_stop').length,
    replacedCount: replaced.length,
    replacedWinCount: replaced.filter((r) => resolvedWin(r) === true).length,
    openCount: rows.filter((r) => r.status === 'open').length,
    missingCount: rows.filter((r) => r.status === 'missing_rates').length,
    significantCount: rows.filter((r) => r.significant_hit === true).length,
  };
}

export interface ConsensusStabilitySummary {
  weighted: boolean;
  nJumps: number;
  medianAbsDelta: number | null;
  signFlipPct: WilsonInterval;
  largeJumpPct: WilsonInterval;
}

function median(values: number[]): number | null {
  if (values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0
    ? (sorted[mid - 1] + sorted[mid]) / 2
    : sorted[mid];
}

export function summarizeConsensusStability(
  rows: FxConsensusEvalRow[],
  opts: { timeframe?: string } = {},
): ConsensusStabilitySummary[] {
  const timeframe = opts.timeframe ?? 'medium';
  const out: ConsensusStabilitySummary[] = [];
  for (const weighted of [true, false]) {
    const jumps = rows.filter(
      (r) =>
        r.timeframe === timeframe &&
        r.weighted === weighted &&
        r.abs_delta_score != null,
    );
    const abs = jumps.map((r) => Number(r.abs_delta_score));
    const flips = jumps.filter((r) => r.sign_flip).length;
    const large = jumps.filter((r) => Number(r.abs_delta_score) >= 1).length;
    out.push({
      weighted,
      nJumps: jumps.length,
      medianAbsDelta: median(abs),
      signFlipPct: wilsonInterval(flips, jumps.length),
      largeJumpPct: wilsonInterval(large, jumps.length),
    });
  }
  return out;
}

export interface ConsensusAccuracySummary {
  interval: WilsonInterval;
  significantInterval: WilsonInterval;
  openCount: number;
  missingCount: number;
}

export function summarizeConsensusAccuracy(
  rows: FxConsensusEvalRow[],
  opts: { timeframe?: string; weighted?: boolean } = {},
): ConsensusAccuracySummary {
  const timeframe = opts.timeframe ?? 'medium';
  const weighted = opts.weighted ?? true;
  const subset = rows.filter((r) => r.timeframe === timeframe && r.weighted === weighted);
  const scored = subset.filter((r) => r.accuracy_status === 'scored');
  let k = 0;
  let n = 0;
  let sigK = 0;
  let sigN = 0;
  for (const r of scored) {
    if (r.hit_5d === null || r.hit_5d === undefined) continue;
    n += 1;
    if (r.hit_5d) k += 1;
    if (r.significant_hit_5d === null || r.significant_hit_5d === undefined) continue;
    sigN += 1;
    if (r.significant_hit_5d) sigK += 1;
  }
  return {
    interval: wilsonInterval(k, n),
    significantInterval: wilsonInterval(sigK, sigN),
    openCount: subset.filter((r) => r.accuracy_status === 'open').length,
    missingCount: subset.filter((r) => r.accuracy_status === 'missing_rates').length,
  };
}

/** Per-day max |Δscore| for the consensus chart jump strip (weighted medium). */
export function buildJumpStripSeries(
  rows: FxConsensusEvalRow[],
  opts: { timeframe?: string; weighted?: boolean } = {},
): Array<{ run_date: string; abs_delta: number | null; large: boolean }> {
  const timeframe = opts.timeframe ?? 'medium';
  const weighted = opts.weighted ?? true;
  const byDate = new Map<string, number>();
  for (const r of rows) {
    if (r.timeframe !== timeframe || r.weighted !== weighted) continue;
    if (r.abs_delta_score == null) continue;
    const v = Math.abs(Number(r.abs_delta_score));
    const prev = byDate.get(r.run_date);
    if (prev == null || v > prev) byDate.set(r.run_date, v);
  }
  return [...byDate.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([run_date, abs_delta]) => ({
      run_date,
      abs_delta,
      large: abs_delta >= 1,
    }));
}

export function openIdeas(rows: FxIdeaEvalRow[]): FxIdeaEvalRow[] {
  return rows
    .filter((r) => r.status === 'open')
    .sort((a, b) => b.run_date.localeCompare(a.run_date) || a.rank - b.rank);
}
