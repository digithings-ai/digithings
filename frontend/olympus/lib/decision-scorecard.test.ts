import { describe, expect, it } from 'vitest';
import {
  bucketFor,
  computeDecisionScorecard,
  convictionBucketCalibration,
  type DecisionRecord,
} from './decision-scorecard';

function rec(conviction: number | null, alpha: number | null, status = 'resolved'): DecisionRecord {
  return { conviction, alpha, status, stance: 'buy' };
}

describe('bucketFor', () => {
  it('thresholds match the Python backtest (high≥4, medium≥2, low otherwise) on positive values', () => {
    expect(bucketFor(5)).toBe('high');
    expect(bucketFor(4)).toBe('high');
    expect(bucketFor(3)).toBe('medium');
    expect(bucketFor(2)).toBe('medium');
    expect(bucketFor(1)).toBe('low');
    expect(bucketFor(0)).toBe('low');
  });

  it('conviction domain is [-5,+5] — negative values bucket by magnitude, not clamped to low', () => {
    // Sell-side calls (negative conviction) should mirror the buy-side buckets.
    expect(bucketFor(-5)).toBe('high');
    expect(bucketFor(-4)).toBe('high');
    expect(bucketFor(-3)).toBe('medium');
    expect(bucketFor(-2)).toBe('medium');
    expect(bucketFor(-1)).toBe('low');
  });
});

describe('computeDecisionScorecard', () => {
  it('returns null when there are no resolved decisions', () => {
    expect(computeDecisionScorecard([])).toBeNull();
    expect(computeDecisionScorecard([rec(5, 0.1, 'pending')])).toBeNull();
  });

  it('computes hit rate, mean/median alpha in percent points, and counts pending', () => {
    const sc = computeDecisionScorecard([
      rec(5, 0.1), // +10% alpha
      rec(4, 0.02), // +2%
      rec(2, -0.03), // −3%
      rec(3, null), // resolved but unpriced → excluded
      rec(5, 0.05, 'pending'), // pending → excluded, counted as pending
    ]);
    expect(sc).not.toBeNull();
    expect(sc!.nResolved).toBe(3);
    expect(sc!.nPending).toBe(1);
    expect(sc!.hitRatePct).toBeCloseTo((2 / 3) * 100, 3); // 2 of 3 positive
    expect(sc!.meanAlphaPct).toBeCloseTo(3, 3); // (10+2−3)/3
    expect(sc!.medianAlphaPct).toBeCloseTo(2, 3);
  });

  it('excludes rows missing conviction from calibration but the scorecard still scores alpha', () => {
    const sc = computeDecisionScorecard([rec(null, 0.1), rec(4, 0.05)]);
    expect(sc!.nResolved).toBe(2);
    // only the conviction-bearing row lands in a bucket
    expect(sc!.buckets.reduce((n, b) => n + b.n, 0)).toBe(1);
  });

  it('flags a well-calibrated book when higher conviction earns higher alpha', () => {
    const sc = computeDecisionScorecard([
      rec(1, -0.02),
      rec(1, 0.0),
      rec(3, 0.02),
      rec(3, 0.03),
      rec(5, 0.08),
      rec(5, 0.1),
    ]);
    expect(sc!.calibrated).toBe(true);
    const byBucket = Object.fromEntries(sc!.buckets.map((b) => [b.bucket, b]));
    expect(byBucket.high.meanAlphaPct).toBeGreaterThan(byBucket.low.meanAlphaPct);
  });

  it('flags a mis-calibrated book when high conviction underperforms', () => {
    const sc = computeDecisionScorecard([
      rec(1, 0.1), // low conviction, big win
      rec(5, -0.05), // high conviction, loss
    ]);
    expect(sc!.calibrated).toBe(false);
  });
});

describe('convictionBucketCalibration', () => {
  it('returns present buckets in ascending conviction order with per-bucket hit rate', () => {
    const decisions = [rec(1, -0.01), rec(2, 0.02), rec(5, 0.06), rec(5, -0.01)];
    const buckets = convictionBucketCalibration(decisions);
    expect(buckets.map((b) => b.bucket)).toEqual(['low', 'medium', 'high']);
    const high = buckets.find((b) => b.bucket === 'high')!;
    expect(high.n).toBe(2);
    expect(high.hitRatePct).toBeCloseTo(50, 3); // 1 of 2 positive
  });
});
