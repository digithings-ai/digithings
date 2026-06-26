/**
 * Pure consensus-average derivations for the twelve-x dashboard.
 *
 * Mirrors the frozen visual-spec demo's `maAt`/`maSeries`: a trailing simple
 * moving average over a window of scored runs. Extends the demo by skipping
 * non-finite scores so a single bad point never poisons the average.
 */

export interface ScorePoint {
  score: number;
}

/**
 * Trailing mean of `series[max(0, i - window + 1) .. i].score`.
 *
 * Returns `null` when `i < 0` or when no finite scores fall in the window.
 * Non-finite scores (NaN, ±Infinity) are skipped rather than counted.
 */
export function consensusAverageAt(series: ScorePoint[], i: number, window = 5): number | null {
  if (i < 0) return null;
  const start = Math.max(0, i - window + 1);
  let sum = 0;
  let n = 0;
  for (let k = start; k <= i && k < series.length; k++) {
    const score = series[k]?.score;
    if (Number.isFinite(score)) {
      sum += score;
      n++;
    }
  }
  return n ? sum / n : null;
}

/** Trailing consensus average at every index. */
export function consensusAverageSeries(series: ScorePoint[], window = 5): (number | null)[] {
  return series.map((_, i) => consensusAverageAt(series, i, window));
}

export interface LatestConsensusAverages {
  avgNow: number | null;
  actualNow: number | null;
  avgYesterday: number | null;
  avgAgo: number | null;
  momentum: number | null;
}

/**
 * Latest-run consensus snapshot: the trailing average now, the raw actual
 * score now, the average one and five runs back, and momentum
 * (`actualNow - avgNow`). All fields are `null` for an empty series.
 */
export function latestConsensusAverages(series: ScorePoint[]): LatestConsensusAverages {
  const lastIdx = series.length - 1;
  const avgNow = consensusAverageAt(series, lastIdx);
  const actualNow = lastIdx >= 0 ? series[lastIdx].score : null;
  const avgYesterday = consensusAverageAt(series, lastIdx - 1);
  const avgAgo = consensusAverageAt(series, lastIdx - 5);
  const momentum = avgNow === null || actualNow === null ? null : actualNow - avgNow;
  return { avgNow, actualNow, avgYesterday, avgAgo, momentum };
}
