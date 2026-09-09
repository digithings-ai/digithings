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

describe('direction-adjusted scoring', () => {
  it('negates alpha for sell stances so negative raw alpha counts as positive directional alpha', () => {
    function recWithStance(
      stance: string,
      alpha: number,
      conviction: number | null = 5
    ): DecisionRecord {
      return { stance, alpha, conviction, status: 'resolved' };
    }
    const sc = computeDecisionScorecard([
      recWithStance('sell', -0.1), // negative raw alpha becomes +10% directional (correct short)
      recWithStance('buy', 0.05), // positive raw alpha stays +5% (correct long)
    ]);
    expect(sc).not.toBeNull();
    expect(sc!.nResolved).toBe(2);
    expect(sc!.hitRatePct).toBe(100); // both are correct directionally
    expect(sc!.meanAlphaPct).toBeCloseTo(7.5, 3); // (10+5)/2
  });

  it('excludes watch stance from headline scoring', () => {
    function recWithStance(
      stance: string,
      alpha: number,
      conviction: number | null = 5
    ): DecisionRecord {
      return { stance, alpha, conviction, status: 'resolved' };
    }
    const sc = computeDecisionScorecard([
      recWithStance('buy', 0.1),
      recWithStance('watch', 0.05), // excluded
      recWithStance('sell', -0.08), // bearish correct = +8% directional
    ]);
    expect(sc).not.toBeNull();
    expect(sc!.nResolved).toBe(2); // watch excluded
    expect(sc!.meanAlphaPct).toBeCloseTo(9, 3); // (10+8)/2, watch excluded
  });
});

describe('episode collapse', () => {
  it('collapses same-ticker same-direction decisions when forward windows overlap', () => {
    // AAPL buy on day 0 for 10 days, then buy again on day 5 for 10 days
    // These overlap (day 5-10), so collapse into one episode
    const decisions: DecisionRecord[] = [
      {
        ticker: 'AAPL',
        run_date: '2024-01-01',
        holding_days: 10,
        stance: 'buy',
        alpha: 0.05,
        conviction: 5,
        status: 'resolved',
      },
      {
        ticker: 'AAPL',
        run_date: '2024-01-06', // day 5
        holding_days: 10,
        stance: 'buy',
        alpha: 0.03,
        conviction: 4,
        status: 'resolved',
      },
    ];
    const sc = computeDecisionScorecard(decisions);
    expect(sc).not.toBeNull();
    expect(sc!.nResolved).toBe(1); // collapsed to one episode
    expect(sc!.meanAlphaPct).toBeCloseTo(5, 3); // uses earliest (first) alpha
  });

  it('creates new episode when direction changes even if ticker is same', () => {
    const decisions: DecisionRecord[] = [
      {
        ticker: 'AAPL',
        run_date: '2024-01-01',
        holding_days: 10,
        stance: 'buy',
        alpha: 0.05,
        conviction: 5,
        status: 'resolved',
      },
      {
        ticker: 'AAPL',
        run_date: '2024-01-06',
        holding_days: 10,
        stance: 'sell', // direction change!
        alpha: -0.03,
        conviction: 4,
        status: 'resolved',
      },
    ];
    const sc = computeDecisionScorecard(decisions);
    expect(sc).not.toBeNull();
    expect(sc!.nResolved).toBe(2); // two episodes due to direction change
  });

  it('keeps different same-direction stances as separate episodes', () => {
    const decisions: DecisionRecord[] = [
      {
        ticker: 'AAPL',
        run_date: '2024-01-01',
        holding_days: 10,
        stance: 'buy',
        alpha: 0.05,
        conviction: 5,
        status: 'resolved',
      },
      {
        ticker: 'AAPL',
        run_date: '2024-01-06',
        holding_days: 10,
        stance: 'hold',
        alpha: 0.03,
        conviction: 4,
        status: 'resolved',
      },
    ];

    expect(computeDecisionScorecard(decisions)!.nResolved).toBe(2);
  });

  it('creates new episode when forward windows do not overlap', () => {
    const decisions: DecisionRecord[] = [
      {
        ticker: 'AAPL',
        run_date: '2024-01-01',
        holding_days: 5,
        stance: 'buy',
        alpha: 0.05,
        conviction: 5,
        status: 'resolved',
      },
      {
        ticker: 'AAPL',
        run_date: '2024-01-10', // starts after first ends (day 6)
        holding_days: 5,
        stance: 'buy',
        alpha: 0.03,
        conviction: 4,
        status: 'resolved',
      },
    ];
    const sc = computeDecisionScorecard(decisions);
    expect(sc).not.toBeNull();
    expect(sc!.nResolved).toBe(2); // two episodes, no overlap
  });
});

describe('information ratio', () => {
  it('computes information ratio as mean alpha divided by std dev of alphas', () => {
    const decisions: DecisionRecord[] = [
      {
        ticker: 'AAPL',
        run_date: '2024-01-01',
        holding_days: 10,
        stance: 'buy',
        alpha: 0.1,
        conviction: 5,
        status: 'resolved',
      },
      {
        ticker: 'MSFT',
        run_date: '2024-01-01',
        holding_days: 10,
        stance: 'buy',
        alpha: 0.02,
        conviction: 4,
        status: 'resolved',
      },
      {
        ticker: 'GOOGL',
        run_date: '2024-01-01',
        holding_days: 10,
        stance: 'buy',
        alpha: -0.03,
        conviction: 3,
        status: 'resolved',
      },
    ];
    const sc = computeDecisionScorecard(decisions);
    expect(sc).not.toBeNull();
    expect(sc!.informationRatio).toBeDefined();
    // Mean = (10+2-3)/3 = 3% directional
    // Std dev of [10, 2, -3] ≈ 5.5 → IR ≈ 3/5.5 ≈ 0.55
    expect(sc!.informationRatio).toBeCloseTo(0.55, 1);
  });
});

describe('calibration evidence state', () => {
  it('reports insufficient when fewer than two buckets have n >= 10', () => {
    const decisions = Array.from({ length: 15 }, (_, i) => ({
      ticker: `T${i}`,
      run_date: '2024-01-01',
      holding_days: 10,
      stance: 'buy',
      alpha: 0.05,
      conviction: 1, // all low conviction
      status: 'resolved' as const,
    }));
    const sc = computeDecisionScorecard(decisions);
    expect(sc).not.toBeNull();
    expect(sc!.calibrationEvidence).toBe('insufficient');
  });

  it('reports aligned when higher conviction earns higher alpha with sufficient evidence', () => {
    // 10 low conviction, 10 high conviction, high outperforms
    const decisions = [
      ...Array.from({ length: 10 }, (_, i) => ({
        ticker: `T${i}`,
        run_date: '2024-01-01',
        holding_days: 10,
        stance: 'buy',
        alpha: 0.02,
        conviction: 1,
        status: 'resolved' as const,
      })),
      ...Array.from({ length: 10 }, (_, i) => ({
        ticker: `T${i + 10}`,
        run_date: '2024-01-01',
        holding_days: 10,
        stance: 'buy',
        alpha: 0.08,
        conviction: 5,
        status: 'resolved' as const,
      })),
    ];
    const sc = computeDecisionScorecard(decisions);
    expect(sc).not.toBeNull();
    expect(sc!.calibrationEvidence).toBe('aligned');
  });

  it('reports inverted when lower conviction earns higher alpha with sufficient evidence', () => {
    // 10 low conviction high alpha, 10 high conviction low alpha
    const decisions = [
      ...Array.from({ length: 10 }, (_, i) => ({
        ticker: `T${i}`,
        run_date: '2024-01-01',
        holding_days: 10,
        stance: 'buy',
        alpha: 0.08,
        conviction: 1,
        status: 'resolved' as const,
      })),
      ...Array.from({ length: 10 }, (_, i) => ({
        ticker: `T${i + 10}`,
        run_date: '2024-01-01',
        holding_days: 10,
        stance: 'buy',
        alpha: 0.02,
        conviction: 5,
        status: 'resolved' as const,
      })),
    ];
    const sc = computeDecisionScorecard(decisions);
    expect(sc).not.toBeNull();
    expect(sc!.calibrationEvidence).toBe('inverted');
  });

  it('does not report inverted for small high-conviction cohorts', () => {
    // 10 low conviction low alpha, 3 high conviction even lower alpha
    // Should be insufficient rather than inverted (not enough high conviction data)
    const decisions = [
      ...Array.from({ length: 10 }, (_, i) => ({
        ticker: `T${i}`,
        run_date: '2024-01-01',
        holding_days: 10,
        stance: 'buy',
        alpha: 0.05,
        conviction: 1,
        status: 'resolved' as const,
      })),
      ...Array.from({ length: 3 }, (_, i) => ({
        ticker: `T${i + 10}`,
        run_date: '2024-01-01',
        holding_days: 10,
        stance: 'buy',
        alpha: 0.01,
        conviction: 5,
        status: 'resolved' as const,
      })),
    ];
    const sc = computeDecisionScorecard(decisions);
    expect(sc).not.toBeNull();
    expect(sc!.calibrationEvidence).toBe('insufficient');
  });
});
