import { describe, expect, it } from 'vitest';
import { summarizeDivergenceAccuracy } from './divergence-accuracy';
import type { FxConsensusDivergence, FxConsensusEvalRow } from './types';

function div(currency: string, isDivergent: boolean): FxConsensusDivergence {
  return {
    currency,
    consensusScore: 1.0,
    consensusTilt: 0.5,
    consensusAsOf: '2026-06-26T00:00:00Z',
    pmtSentiment: 'bearish',
    pmtScore: -1.25,
    pmtAsOf: '2026-06-21',
    gap: 2.25,
    isDivergent,
    snapshotId: null,
    rawSnapshot: null,
    streetStatement: '',
    pmtStatement: '',
  };
}

function scored(currency: string, hit_5d: boolean | null): FxConsensusEvalRow {
  return {
    run_date: '2026-06-13',
    currency,
    timeframe: 'medium',
    weighted: true,
    score: 0.5,
    tilt: 0.2,
    agreement: 0.4,
    n_brokers: 4,
    n_brokers_prev: 4,
    delta_score: 0.1,
    delta_tilt: 0.1,
    delta_agreement: 0,
    delta_score_pred: 0.1,
    clip_flag: false,
    sign_flip: false,
    abs_delta_score: 0.1,
    accuracy_status: 'scored',
    currency_ret_5d: 0.01,
    sigma_entry: 0.005,
    hit_5d,
    significant_hit_5d: null,
    as_of: '2026-06-26T00:00:00Z',
  };
}

describe('summarizeDivergenceAccuracy', () => {
  it('splits scored rows by the current divergent flag', () => {
    const summary = summarizeDivergenceAccuracy(
      { EUR: div('EUR', true), GBP: div('GBP', false) },
      [scored('EUR', true), scored('EUR', false), scored('GBP', true), scored('GBP', null)],
    );
    expect(summary.divergent.n).toBe(2);
    expect(summary.divergent.k).toBe(1);
    expect(summary.aligned.n).toBe(1);
    expect(summary.aligned.k).toBe(1);
  });

  it('ignores unscored rows and pins timeframe/weighted', () => {
    const summary = summarizeDivergenceAccuracy({ EUR: div('EUR', true) }, [
      { ...scored('EUR', true), accuracy_status: 'carried' },
      { ...scored('EUR', true), timeframe: 'long' },
      { ...scored('EUR', true), weighted: false },
    ]);
    expect(summary.divergent.n).toBe(0);
    expect(summary.aligned.n).toBe(0);
  });

  it('buckets unknown currencies as aligned', () => {
    const summary = summarizeDivergenceAccuracy({}, [scored('JPY', true)]);
    expect(summary.aligned.n).toBe(1);
  });
});
