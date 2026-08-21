/**
 * Pure aggregations for the Track record tab from eval table rows.
 */
import { wilsonInterval, type WilsonInterval } from './wilson';
import type { FxConsensusEvalRow, FxIdeaEvalRow } from './types';

export interface HitRateSummary {
  label: string;
  horizonDays: number;
  significant: boolean;
  interval: WilsonInterval;
  longInterval: WilsonInterval;
  shortInterval: WilsonInterval;
  openCount: number;
  missingCount: number;
  unscoredNeither: number;
}

function countHits(
  rows: FxIdeaEvalRow[],
  opts: { significant: boolean; direction?: string },
): { k: number; n: number; neither: number } {
  let k = 0;
  let n = 0;
  let neither = 0;
  for (const r of rows) {
    if (opts.direction && r.direction.toLowerCase() !== opts.direction) continue;
    if (r.status !== 'scored') continue;
    const flag = opts.significant ? r.significant_hit : r.hit;
    if (flag === null || flag === undefined) {
      neither += 1;
      continue;
    }
    n += 1;
    if (flag) k += 1;
  }
  return { k, n, neither };
}

export function summarizeIdeaHits(rows: FxIdeaEvalRow[]): HitRateSummary[] {
  const out: HitRateSummary[] = [];
  for (const horizonDays of [5, 1] as const) {
    const subset = rows.filter((r) => r.horizon_days === horizonDays);
    const openCount = new Set(
      subset.filter((r) => r.status === 'open').map((r) => `${r.run_date}:${r.rank}`),
    ).size;
    const missingCount = new Set(
      subset
        .filter((r) => r.status === 'missing_rates')
        .map((r) => `${r.run_date}:${r.rank}`),
    ).size;

    for (const significant of [false, true]) {
      const all = countHits(subset, { significant });
      const longs = countHits(subset, { significant, direction: 'long' });
      const shorts = countHits(subset, { significant, direction: 'short' });
      out.push({
        label:
          horizonDays === 5
            ? significant
              ? '5d significant hit'
              : '5d directional hit'
            : significant
              ? '1d significant hit (noisy)'
              : '1d directional hit (noisy)',
        horizonDays,
        significant,
        interval: wilsonInterval(all.k, all.n),
        longInterval: wilsonInterval(longs.k, longs.n),
        shortInterval: wilsonInterval(shorts.k, shorts.n),
        openCount,
        missingCount,
        unscoredNeither: all.neither,
      });
    }
  }
  return out;
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
    .filter((r) => r.horizon_days === 5 && r.status === 'open')
    .sort((a, b) => b.run_date.localeCompare(a.run_date) || a.rank - b.rank);
}
