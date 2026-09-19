import { describe, expect, it } from 'vitest';
import {
  assembleConsensusDivergence,
  countDisputedTradeIdeas,
  DEFAULT_DIVERGENCE_THRESHOLD,
  disputedTradeIdeaRanks,
  isTradeIdeaDisputed,
  mapSmartBiasSentiment,
  pairCurrencies,
} from './divergence';
import type { FxConsensusSnapshotRow, FxTradeIdeaRow } from './types';

function consensusRow(
  currency: string,
  score: number,
  tilt = 0.5,
): FxConsensusSnapshotRow {
  return {
    run_date: '2026-07-28',
    currency,
    timeframe: 'medium',
    horizon_weeks: null,
    weighted: true,
    score,
    confidence: 0.7,
    agreement: 0.6,
    tilt,
    n_eff: 5,
    n_brokers: 5,
    n_views: 8,
    bullish_pct: 0.5,
    bearish_pct: 0.3,
    neutral_pct: 0.1,
    watch_pct: 0.1,
    as_of: '2026-07-28T12:00:00Z',
  };
}

describe('mapSmartBiasSentiment', () => {
  it('maps the categorical ladder', () => {
    expect(mapSmartBiasSentiment('very bullish')).toBe(2);
    expect(mapSmartBiasSentiment('weak bullish')).toBe(0.75);
    expect(mapSmartBiasSentiment('bearish')).toBe(-1.25);
    expect(mapSmartBiasSentiment('neutral')).toBe(0);
  });

  it('returns null for unknown labels', () => {
    expect(mapSmartBiasSentiment('uptrend')).toBeNull();
    expect(mapSmartBiasSentiment('')).toBeNull();
  });
});

describe('assembleConsensusDivergence', () => {
  const snapshot = { id: 'snap-1', payload: { data: [] } };

  it('flags divergent reads beyond threshold', () => {
    const joined = assembleConsensusDivergence(
      [consensusRow('EUR', 1.5)],
      [{ currency: 'EUR', overall_sentiment: 'bearish', week_first_date: '2026-07-21' }],
      snapshot,
      DEFAULT_DIVERGENCE_THRESHOLD,
    );
    expect(joined.EUR.isDivergent).toBe(true);
    expect(joined.EUR.gap).toBeGreaterThanOrEqual(DEFAULT_DIVERGENCE_THRESHOLD);
    expect(joined.EUR.pmtStatement).toContain('Overall_Sentiment=bearish');
    expect(joined.EUR.rawSnapshot).toEqual(snapshot.payload);
  });

  it('does not flag when gap is below threshold', () => {
    const joined = assembleConsensusDivergence(
      [consensusRow('USD', 1.2)],
      [{ currency: 'USD', overall_sentiment: 'bullish', week_first_date: '2026-07-21' }],
      snapshot,
      DEFAULT_DIVERGENCE_THRESHOLD,
    );
    expect(joined.USD.isDivergent).toBe(false);
  });

  it('omits currencies without smart-bias rows', () => {
    const joined = assembleConsensusDivergence([consensusRow('JPY', 1.0)], [], snapshot);
    expect(joined.JPY).toBeUndefined();
  });
});

describe('trade idea disputes', () => {
  const idea: FxTradeIdeaRow = {
    run_date: '2026-07-28',
    rank: 1,
    pair: 'EUR/USD',
    direction: 'short',
    title: 'EUR short',
    thesis: '',
    catalyst: '',
    levels: [],
    citations: [],
    as_of: '2026-07-28T12:00:00Z',
  };

  const byCurrency = assembleConsensusDivergence(
    [consensusRow('EUR', 1.5), consensusRow('USD', 0.2)],
    [
      { currency: 'EUR', overall_sentiment: 'bearish', week_first_date: '2026-07-21' },
      { currency: 'USD', overall_sentiment: 'neutral', week_first_date: '2026-07-21' },
    ],
    null,
  );

  it('parses pair legs', () => {
    expect(pairCurrencies('eur/usd')).toEqual(['EUR', 'USD']);
  });

  it('counts ideas touching a divergent currency', () => {
    expect(isTradeIdeaDisputed(idea, byCurrency)).toBe(true);
    expect(countDisputedTradeIdeas([idea], byCurrency)).toBe(1);
    expect(disputedTradeIdeaRanks([idea], byCurrency)).toEqual([1]);
  });
});
