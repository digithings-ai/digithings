import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import {
  summarizeConsensusAccuracy,
  summarizeConsensusStability,
  summarizeIdeaOutcomes,
} from '@/lib/twelve-x/track-record';
import type { FxConsensusEvalRow, FxIdeaEvalRow } from '@/lib/twelve-x/types';
import CalibrationPanel from './CalibrationPanel';

function idea(partial: Partial<FxIdeaEvalRow>): FxIdeaEvalRow {
  return {
    run_date: '2026-06-12',
    rank: 1,
    horizon_days: 0,
    pair: 'EUR/USD',
    direction: 'long',
    status: 'resolved',
    entry_date: null,
    exit_date: null,
    entry_fix: null,
    exit_fix: null,
    ret: null,
    hold_return: 0.02,
    sigma_entry: null,
    hit: true,
    directional_win: true,
    significant_hit: true,
    n_sessions: 3,
    as_of: '2026-06-26T00:00:00Z',
    ...partial,
  };
}

function consensusEval(partial: Partial<FxConsensusEvalRow>): FxConsensusEvalRow {
  return {
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
    ...partial,
  };
}

describe('CalibrationPanel', () => {
  it('renders idea, stability, and accuracy sections wired to the summarize outputs', () => {
    const html = renderToStaticMarkup(
      createElement(CalibrationPanel, {
        ideaSummary: summarizeIdeaOutcomes([
          idea({}),
          idea({ rank: 2, direction: 'short', hold_return: -0.01, directional_win: false, hit: false, significant_hit: false }),
          idea({ rank: 3, status: 'carried', hit: null, directional_win: null, significant_hit: false }),
        ]),
        consensusStability: summarizeConsensusStability([consensusEval({})]),
        consensusAccuracy: summarizeConsensusAccuracy([consensusEval({})]),
      }),
    );
    expect(html).toContain('Calibration');
    expect(html).toContain('Idea outcomes');
    expect(html).toContain('Consensus stability');
    expect(html).toContain('Consensus 5-day accuracy');
    expect(html).toContain('All ideas');
    expect(html).toContain('Carried (raw)');
    expect(html).toContain('95% CI');
  });

  it('renders an empty state when there is no consensus jump data', () => {
    const html = renderToStaticMarkup(
      createElement(CalibrationPanel, {
        ideaSummary: summarizeIdeaOutcomes([]),
        consensusStability: [],
        consensusAccuracy: summarizeConsensusAccuracy([]),
      }),
    );
    expect(html).toContain('No consensus jump data yet.');
    // n=0 intervals still render the em-dash WilsonStat.
    expect(html).toContain('—');
  });
});
