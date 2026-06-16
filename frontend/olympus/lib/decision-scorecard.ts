/**
 * Decision scorecard — conviction calibration for the Observability dashboard (Pillar 3D).
 *
 * Pure functions over resolved `decision_log` rows. The central question: do **higher-
 * conviction** calls earn **higher alpha**? `alpha` is the realized excess return over the
 * benchmark (SPY) computed at resolution time, stored as a FRACTION (0.05 = +5%); we surface
 * percent points. Conviction is the 0..5 effective conviction recorded with each decision.
 *
 * Buckets mirror the Python backtest core (digiquant/src/digiquant/olympus/atlas/backtest.py):
 * high ≥ 4, medium ≥ 2, low otherwise — so the in-graph backtest and this dashboard agree.
 */

/** Conviction thresholds — kept in sync with backtest.py `_HIGH_CONVICTION` / `_MED_CONVICTION`. */
const HIGH_CONVICTION = 4;
const MED_CONVICTION = 2;

export type ConvictionBucket = 'low' | 'medium' | 'high';

/** Minimal shape consumed from a `decision_log` row (alpha is a fraction). */
export interface DecisionRecord {
  conviction: number | null;
  alpha: number | null;
  status: string;
  stance?: string | null;
}

export interface BucketCalibration {
  bucket: ConvictionBucket;
  n: number;
  meanAlphaPct: number;
  hitRatePct: number; // share of decisions with alpha > 0 (0..100)
  meanConviction: number;
}

export interface DecisionScorecard {
  nResolved: number;
  nPending: number;
  hitRatePct: number; // overall share with positive alpha (0..100)
  meanAlphaPct: number;
  medianAlphaPct: number;
  buckets: BucketCalibration[]; // present buckets, ascending conviction (low → high)
  /** True when mean alpha is non-decreasing across present buckets (the calibration we want). */
  calibrated: boolean;
}

function mean(xs: number[]): number {
  return xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0;
}

function median(xs: number[]): number {
  if (!xs.length) return 0;
  const s = [...xs].sort((a, b) => a - b);
  const mid = Math.floor(s.length / 2);
  return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
}

function round4(x: number): number {
  return Math.round(x * 1e4) / 1e4;
}

export function bucketFor(conviction: number): ConvictionBucket {
  if (conviction >= HIGH_CONVICTION) return 'high';
  if (conviction >= MED_CONVICTION) return 'medium';
  return 'low';
}

/** A resolved decision with a realized alpha scores the overall track record (conviction optional). */
function hasResolvedAlpha(d: DecisionRecord): d is DecisionRecord & { alpha: number } {
  return d.status === 'resolved' && d.alpha != null;
}

/** Calibration additionally needs a recorded conviction to place the row in a bucket. */
function isCalibratable(
  d: DecisionRecord
): d is DecisionRecord & { conviction: number; alpha: number } {
  return hasResolvedAlpha(d) && d.conviction != null;
}

/** Per-bucket calibration over resolved decisions, ascending conviction; empty buckets omitted. */
export function convictionBucketCalibration(decisions: DecisionRecord[]): BucketCalibration[] {
  const order: ConvictionBucket[] = ['low', 'medium', 'high'];
  const grouped: Record<ConvictionBucket, { alphas: number[]; convs: number[] }> = {
    low: { alphas: [], convs: [] },
    medium: { alphas: [], convs: [] },
    high: { alphas: [], convs: [] },
  };
  for (const d of decisions) {
    if (!isCalibratable(d)) continue;
    const g = grouped[bucketFor(d.conviction)];
    g.alphas.push(d.alpha);
    g.convs.push(d.conviction);
  }
  const out: BucketCalibration[] = [];
  for (const bucket of order) {
    const { alphas, convs } = grouped[bucket];
    if (!alphas.length) continue;
    out.push({
      bucket,
      n: alphas.length,
      meanAlphaPct: round4(mean(alphas) * 100),
      hitRatePct: round4((alphas.filter((a) => a > 0).length / alphas.length) * 100),
      meanConviction: round4(mean(convs)),
    });
  }
  return out;
}

/** Overall scorecard; null when there are no resolved decisions to score. */
export function computeDecisionScorecard(decisions: DecisionRecord[]): DecisionScorecard | null {
  const scored = decisions.filter(hasResolvedAlpha);
  if (!scored.length) return null;
  const alphas = scored.map((d) => d.alpha);
  const buckets = convictionBucketCalibration(decisions);
  // Calibrated = mean alpha never falls as conviction rises across the present buckets.
  let calibrated = true;
  for (let i = 1; i < buckets.length; i++) {
    if (buckets[i].meanAlphaPct < buckets[i - 1].meanAlphaPct) {
      calibrated = false;
      break;
    }
  }
  return {
    nResolved: scored.length,
    nPending: decisions.filter((d) => d.status === 'pending').length,
    hitRatePct: round4((alphas.filter((a) => a > 0).length / alphas.length) * 100),
    meanAlphaPct: round4(mean(alphas) * 100),
    medianAlphaPct: round4(median(alphas) * 100),
    buckets,
    calibrated,
  };
}
