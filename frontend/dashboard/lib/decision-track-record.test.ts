import { describe, expect, it } from 'vitest';
import { backtestDecisions, type DecisionInput } from './decision-track-record';

const d = (
  run_date: string,
  return_frac: number,
  benchmark_frac: number,
  conviction: number | null,
): DecisionInput => ({ run_date, return_frac, benchmark_frac, conviction, holding_days: 10 });

describe('backtestDecisions (parity with atlas/backtest.py)', () => {
  it('empty → zeroed record', () => {
    const r = backtestDecisions([]);
    expect(r.n_trades).toBe(0);
    expect(r.hit_rate).toBe(0);
    expect(r.information_ratio).toBe(0);
    expect(r.sortino_ratio).toBe(0);
    expect(r.conviction_buckets).toEqual([]);
  });

  it('hit_rate / mean / median alpha in percent points, rounded to 4dp', () => {
    // alphas: +0.04, -0.01, +0.02  → mean 0.0166.., median 0.02
    const r = backtestDecisions([
      d('2026-06-23', 0.05, 0.01, 5),
      d('2026-06-23', 0.0, 0.01, 2),
      d('2026-06-23', 0.03, 0.01, 5),
    ]);
    expect(r.n_trades).toBe(3);
    expect(r.hit_rate).toBe(0.6667); // 2 of 3 positive
    expect(r.mean_alpha_pct).toBe(1.6667);
    expect(r.median_alpha_pct).toBe(2);
  });

  it('information ratio = mean(alpha)/std(alpha) (population std, NOT annualized)', () => {
    // alphas +0.04, -0.01, +0.02; mean 0.016666..; population variance = mean of squared devs
    const r = backtestDecisions([
      d('2026-06-23', 0.05, 0.01, 5),
      d('2026-06-23', 0.0, 0.01, 2),
      d('2026-06-23', 0.03, 0.01, 5),
    ]);
    // std over [0.04,-0.01,0.02] (population): ~0.0205480 → IR ~0.8111
    // (matches backtest.py's round(mean/std, 4); the plan's 0.8058 used a slightly
    // wrong std estimate of 0.020683 — the true population std is 0.0205480).
    expect(r.information_ratio).toBeCloseTo(0.8111, 3);
  });

  it('sortino falls back to information ratio when no downside (all alpha ≥ 0)', () => {
    const r = backtestDecisions([
      d('2026-06-23', 0.05, 0.01, 5),
      d('2026-06-23', 0.04, 0.01, 4),
    ]);
    expect(r.sortino_ratio).toBe(r.information_ratio);
  });

  it('max drawdown is worst peak-to-trough of the compounded decision returns (negative pct)', () => {
    // returns +0.10 then -0.20 → nav 1.10 then 0.88; dd from peak 1.10 = -20%
    const r = backtestDecisions([
      d('2026-06-23', 0.1, 0.0, 3),
      d('2026-06-24', -0.2, 0.0, 3),
    ]);
    expect(r.max_drawdown_pct).toBeCloseTo(-20, 4);
  });

  it('conviction buckets group by |conviction| (high≥4, medium≥2, low<2), mean alpha pct + n', () => {
    const r = backtestDecisions([
      d('2026-06-23', 0.06, 0.01, 5), // high, alpha +5%
      d('2026-06-23', 0.04, 0.01, 4), // high, alpha +3%
      d('2026-06-23', 0.02, 0.01, 2), // medium, alpha +1%
      d('2026-06-23', 0.0, 0.01, -5), // high (|conv|=5), alpha -1%
    ]);
    const high = r.conviction_buckets.find((b) => b.conviction === 5);
    // emit one bucket entry per present bucket, keyed by a representative conviction:
    // map 'high'→5, 'medium'→3, 'low'→1 (so the chart x-axis is monotone)
    expect(high?.n).toBe(3);
    expect(high?.mean_alpha_pct).toBeCloseTo((5 + 3 - 1) / 3, 4);
  });
});
