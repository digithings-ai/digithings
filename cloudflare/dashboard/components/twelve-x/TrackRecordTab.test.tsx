import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import type { FxConsensusEvalRow, FxIdeaEvalRow, FxTradeIdeaRow } from '@/lib/twelve-x/types';
import TrackRecordTab from './TrackRecordTab';

function idea(partial: Partial<FxIdeaEvalRow> & Pick<FxIdeaEvalRow, 'run_date' | 'rank'>): FxIdeaEvalRow {
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

function archiveRow(partial: Partial<FxTradeIdeaRow> & Pick<FxTradeIdeaRow, 'run_date' | 'rank'>): FxTradeIdeaRow {
  return {
    pair: 'EUR/USD',
    direction: 'long',
    title: 'EUR/USD long idea',
    thesis: 'thesis',
    catalyst: 'catalyst',
    levels: [],
    citations: [],
    as_of: '2026-06-26T00:00:00Z',
    ...partial,
  };
}

describe('TrackRecordTab', () => {
  it('renders calibration wired to the raw eval rows plus the open-ideas list', () => {
    const html = renderToStaticMarkup(
      createElement(TrackRecordTab, {
        ideas: [archiveRow({ run_date: '2026-06-26', rank: 1 })],
        ideaEvalRaw: [
          idea({ run_date: '2026-06-12', rank: 1 }),
          idea({ run_date: '2026-06-26', rank: 1, status: 'carried', hit: null, directional_win: null }),
        ],
        consensusEval: [] as FxConsensusEvalRow[],
      }),
    );
    expect(html).toContain('Track record');
    expect(html).toContain('Calibration');
    expect(html).toContain('Open ideas');
    expect(html).toContain('EUR/USD');
  });

  it('renders an empty open-ideas state when nothing is carried', () => {
    const html = renderToStaticMarkup(
      createElement(TrackRecordTab, {
        ideas: [],
        ideaEvalRaw: [idea({ run_date: '2026-06-12', rank: 1 })],
        consensusEval: [],
      }),
    );
    expect(html).toContain('nothing currently live');
  });

  it('renders the bank-vs-quant corroboration section when divergence reads exist', () => {
    const html = renderToStaticMarkup(
      createElement(TrackRecordTab, {
        ideas: [],
        ideaEvalRaw: [idea({ run_date: '2026-06-12', rank: 1 })],
        consensusEval: [],
        divergenceByCurrency: {
          EUR: {
            currency: 'EUR',
            consensusScore: 1.0,
            consensusTilt: 0.5,
            consensusAsOf: '2026-06-26T00:00:00Z',
            pmtSentiment: 'bearish',
            pmtScore: -1.0,
            pmtAsOf: '2026-06-21',
            gap: 2.0,
            isDivergent: true,
            snapshotId: null,
            rawSnapshot: null,
            streetStatement: '',
            pmtStatement: '',
          },
        },
        series: [],
      }),
    );
    expect(html).toContain('Bank vs quant');
    expect(html).toContain('Divergent-call accuracy');
  });

  it('renders recent idea rows joined to their eval rows', () => {
    const html = renderToStaticMarkup(
      createElement(TrackRecordTab, {
        ideas: [archiveRow({ run_date: '2026-06-26', rank: 1 })],
        ideaEvalRaw: [idea({ run_date: '2026-06-26', rank: 1 })],
        consensusEval: [],
      }),
    );
    expect(html).toContain('Recent ideas · levels vs fix');
    expect(html).toContain('resolved');
    // LevelFixSection is client-fetched: static markup shows its loading state.
    expect(html).toContain('Loading fix series');
  });
});
