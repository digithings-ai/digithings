import { describe, expect, it } from 'vitest';
import { formatWilsonPct, wilsonInterval } from './wilson';
import {
  openIdeas,
  summarizeConsensusAccuracy,
  summarizeConsensusStability,
  summarizeIdeaOutcomes,
} from './track-record';
import type { FxConsensusEvalRow, FxIdeaEvalRow } from './types';

describe('wilsonInterval', () => {
  it('matches the classic 7/10 interval', () => {
    const iv = wilsonInterval(7, 10);
    expect(iv.rate).toBeCloseTo(0.7);
    expect(iv.low).toBeGreaterThan(0.39);
    expect(iv.low).toBeLessThan(0.41);
    expect(iv.high).toBeGreaterThan(0.89);
    expect(iv.high).toBeLessThan(0.9);
    expect(formatWilsonPct(iv)).toContain('n=10');
  });

  it('handles empty n', () => {
    expect(wilsonInterval(0, 0)).toEqual({ low: 0, high: 1, n: 0, k: 0, rate: 0 });
  });
});

function idea(
  partial: Partial<FxIdeaEvalRow> & Pick<FxIdeaEvalRow, 'run_date' | 'rank'>,
): FxIdeaEvalRow {
  return {
    horizon_days: 0,
    pair: 'EUR/USD',
    direction: 'long',
    status: 'resolved',
    entry_date: null,
    exit_date: null,
    entry_fix: null,
    exit_fix: null,
    ret: null,
    hold_return: 0.01,
    sigma_entry: null,
    hit: true,
    directional_win: true,
    significant_hit: true,
    n_sessions: 3,
    as_of: '2026-06-26T00:00:00Z',
    ...partial,
  };
}

describe('summarizeIdeaOutcomes', () => {
  it('counts successor-resolved directional wins; open excluded from n', () => {
    const rows = [
      idea({
        run_date: '2026-06-12',
        rank: 1,
        status: 'resolved',
        hold_return: 0.02,
        directional_win: true,
        hit: true,
      }),
      idea({
        run_date: '2026-06-12',
        rank: 2,
        direction: 'short',
        status: 'resolved',
        hold_return: -0.01,
        hit: false,
        directional_win: false,
        significant_hit: false,
      }),
      idea({
        run_date: '2026-06-19',
        rank: 1,
        status: 'resolved',
        hold_return: 0,
        hit: false,
        directional_win: false,
        significant_hit: false,
      }),
      idea({
        run_date: '2026-06-26',
        rank: 1,
        status: 'open',
        hit: null,
        directional_win: null,
        significant_hit: false,
      }),
      idea({
        run_date: '2026-06-27',
        rank: 1,
        status: 'missing_rates',
        hit: null,
        directional_win: null,
        significant_hit: null,
      }),
    ];
    const summary = summarizeIdeaOutcomes(rows);
    expect(summary.interval.n).toBe(3);
    expect(summary.interval.k).toBe(1);
    expect(summary.resolvedCount).toBe(3);
    expect(summary.winCount).toBe(1);
    expect(summary.lossCount).toBe(2);
    expect(summary.openCount).toBe(1);
    expect(summary.missingCount).toBe(1);
    expect(openIdeas(rows)).toHaveLength(1);
  });
});

describe('consensus stability', () => {
  const evalRows: FxConsensusEvalRow[] = [
    {
      run_date: '2026-06-13',
      currency: 'EUR',
      timeframe: 'medium',
      weighted: true,
      score: -0.6,
      tilt: -0.5,
      agreement: 0.1,
      n_brokers: 4,
      n_brokers_prev: 4,
      delta_score: -1.1,
      delta_tilt: -0.9,
      delta_agreement: -0.1,
      delta_score_pred: -1.0,
      clip_flag: false,
      sign_flip: true,
      abs_delta_score: 1.1,
      accuracy_status: 'scored',
      currency_ret_5d: 0.01,
      sigma_entry: 0.005,
      hit_5d: true,
      significant_hit_5d: true,
      as_of: '2026-06-26T00:00:00Z',
    },
    {
      run_date: '2026-06-13',
      currency: 'GBP',
      timeframe: 'medium',
      weighted: true,
      score: 0.2,
      tilt: 0.1,
      agreement: 0.1,
      n_brokers: 3,
      n_brokers_prev: 3,
      delta_score: 0.2,
      delta_tilt: 0.1,
      delta_agreement: 0,
      delta_score_pred: 0.1,
      clip_flag: false,
      sign_flip: false,
      abs_delta_score: 0.2,
      accuracy_status: 'open',
      currency_ret_5d: null,
      sigma_entry: null,
      hit_5d: null,
      significant_hit_5d: null,
      as_of: '2026-06-26T00:00:00Z',
    },
  ];

  it('summarizes sign-flip and large-jump rates', () => {
    const [weighted] = summarizeConsensusStability(evalRows);
    expect(weighted.nJumps).toBe(2);
    expect(weighted.signFlipPct.k).toBe(1);
    expect(weighted.largeJumpPct.k).toBe(1);
    expect(weighted.medianAbsDelta).toBeCloseTo(0.65);
  });

  it('summarizes 5d accuracy', () => {
    const acc = summarizeConsensusAccuracy(evalRows);
    expect(acc.interval.n).toBe(1);
    expect(acc.interval.k).toBe(1);
    expect(acc.openCount).toBe(1);
  });
});
