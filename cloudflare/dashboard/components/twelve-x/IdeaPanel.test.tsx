import { describe, expect, it, vi } from 'vitest';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

import IdeaPanel, { IdeaPanelBody, IdeaLifecycleBlock } from './IdeaPanel';
import { TwelveXProvider } from './context';
import type { TradeHistoryRow } from '@/lib/twelve-x/trade-history';
import type { FxIdeaEvalRow, FxTradeIdeaRow } from '@/lib/twelve-x/types';

function row(partial: Partial<TradeHistoryRow>): TradeHistoryRow {
  return {
    runDate: '2026-07-24',
    rank: 1,
    pair: 'USD/JPY',
    direction: 'long',
    title: 'USD/JPY long',
    catalyst: '',
    entryBand: '148.20–148.60',
    stop: '147.40',
    target: '150.50',
    hasLevels: true,
    lifecycle: 'closed',
    entryDate: '2026-07-24',
    exitDate: '2026-07-29',
    sessions: 5,
    holdReturn: 0.012,
    maxFavorable: 0.02,
    maxAdverse: -0.005,
    directionalWin: true,
    ...partial,
  };
}

describe('IdeaLifecycleBlock', () => {
  it('renders the one-word status, the grade and the measured final impact', () => {
    const html = renderToStaticMarkup(
      createElement(IdeaLifecycleBlock, {
        row: row({
          lifecycle: 'closed',
          levelOutcome: 'target',
          outcome: 'right',
          gradeBasis: 'measured',
          closedBy: 'target',
          exitDate: '2026-07-29',
        }),
      }),
    );
    expect(html).toContain('Lifecycle');
    expect(html).toContain('Status');
    expect(html).toContain('Target');
    expect(html).toContain('Right');
    expect(html).toContain('Final impact');
    expect(html).toContain('+1.2%');
    expect(html).toContain('Closed 2026-07-29');
  });

  it('shows the directional basis for a never-filled idea', () => {
    const html = renderToStaticMarkup(
      createElement(IdeaLifecycleBlock, {
        row: row({
          lifecycle: 'closed',
          levelOutcome: 'no_entry',
          gradeBasis: 'directional',
          outcome: 'wrong',
          holdReturn: -0.004,
          exitDate: '2026-07-29',
        }),
      }),
    );
    expect(html).toContain('Superseded');
    expect(html).toContain('Wrong');
    expect(html).toContain('-0.4%');
    expect(html).toContain('entry never filled');
  });
});

const idea: FxTradeIdeaRow = {
  run_date: '2026-07-24',
  rank: 1,
  pair: 'USD/JPY',
  direction: 'long',
  title: 'USD/JPY long',
  thesis: 'BoJ normalization path repricing.',
  catalyst: 'BoJ minutes',
  levels: [],
  citations: [{ broker: 'Desk Alpha', source_file: 'alpha/usdjpy.md' }],
  as_of: '2026-07-24T00:00:00Z',
};

const evalRow: FxIdeaEvalRow = {
  run_date: '2026-07-24',
  rank: 1,
  horizon_days: 0,
  pair: 'USD/JPY',
  direction: 'long',
  status: 'resolved',
  entry_date: '2026-07-24',
  exit_date: '2026-07-29',
  entry_fix: 148.2,
  exit_fix: 149,
  ret: 0.012,
  hold_return: 0.012,
  sigma_entry: 0.004,
  hit: true,
  directional_win: true,
  significant_hit: true,
  n_sessions: 5,
  as_of: '2026-07-29T00:00:00Z',
  outcome: 'right',
  grade_basis: 'measured',
  closed_by: 'successor',
};

function panel(open: boolean, runDate: string | null, rank: number | null) {
  return renderToStaticMarkup(
    createElement(TwelveXProvider, {
      value: {
        runDate: '2026-07-24',
        crossLink: vi.fn(),
        openBrief: vi.fn(),
        openIdea: vi.fn(),
        watchlist: { tickers: [], has: () => false, toggle: vi.fn() } as never,
      },
      children: createElement(IdeaPanel, {
        open,
        runDate,
        rank,
        ideas: [idea],
        ideaEval: [evalRow],
        onClose: vi.fn(),
      }),
    } as never),
  );
}

function body(ideaRow: FxTradeIdeaRow | null) {
  return renderToStaticMarkup(
    createElement(TwelveXProvider, {
      value: {
        runDate: '2026-07-24',
        crossLink: vi.fn(),
        openBrief: vi.fn(),
        openIdea: vi.fn(),
        watchlist: { tickers: [], has: () => false, toggle: vi.fn() } as never,
      },
      children: createElement(IdeaPanelBody, { idea: ideaRow, ideaEval: [evalRow] }),
    } as never),
  );
}

describe('IdeaPanel', () => {
  it('renders the idea argument and lifecycle for a known row', () => {
    const html = body(idea);
    expect(html).toContain('BoJ normalization path repricing.');
    expect(html).toContain('Lifecycle');
    expect(html).toContain('Source briefs');
    expect(html).toContain('alpha/usdjpy.md');
  });

  it('renders an empty state for an unknown row', () => {
    expect(body(null)).toContain('Trade idea not found');
  });

  it('renders nothing while closed', () => {
    expect(panel(false, '2026-07-24', 1)).toBe('');
  });
});
