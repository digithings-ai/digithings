import { describe, expect, it, vi } from 'vitest';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

import IdeaCardsIndex from './IdeaCardsIndex';
import { TwelveXProvider } from './context';
import type { FxIdeaEvalRow, FxTradeIdeaRow } from '@/lib/twelve-x/types';

const liveIdea: FxTradeIdeaRow = {
  run_date: '2026-07-24',
  rank: 1,
  pair: 'USD/JPY',
  direction: 'long',
  title: 'USD/JPY long',
  thesis: 'thesis',
  catalyst: 'data',
  levels: [],
  citations: [],
  as_of: '2026-07-24T00:00:00Z',
};

const closedIdea: FxTradeIdeaRow = {
  ...liveIdea,
  run_date: '2026-07-06',
  pair: 'EUR/USD',
  direction: 'short',
  title: 'EUR/USD short',
};

const liveEval: FxIdeaEvalRow = {
  run_date: '2026-07-24',
  rank: 1,
  horizon_days: 0,
  pair: 'USD/JPY',
  direction: 'long',
  status: 'carried',
  entry_date: '2026-07-24',
  exit_date: null,
  entry_fix: 148,
  exit_fix: null,
  ret: 0.004,
  hold_return: 0.004,
  sigma_entry: 0.004,
  hit: null,
  directional_win: null,
  significant_hit: null,
  n_sessions: 4,
  as_of: '2026-07-29T00:00:00Z',
};

const closedEval: FxIdeaEvalRow = {
  ...liveEval,
  run_date: '2026-07-06',
  pair: 'EUR/USD',
  direction: 'short',
  status: 'resolved',
  exit_date: '2026-07-10',
  exit_fix: 1.09,
  n_sessions: 4,
  directional_win: true,
  outcome: 'right',
  grade_basis: 'measured',
  closed_by: 'successor',
};

function render(openIdea = vi.fn()) {
  return renderToStaticMarkup(
    createElement(TwelveXProvider, {
      value: {
        runDate: '2026-07-24',
        crossLink: vi.fn(),
        openBrief: vi.fn(),
        openIdea,
        watchlist: { tickers: [], has: () => false, toggle: vi.fn() } as never,
      },
      children: createElement(IdeaCardsIndex, {
        ideas: [liveIdea, closedIdea],
        ideaEval: [liveEval, closedEval],
        onBack: vi.fn(),
      }),
    } as never),
  );
}

describe('IdeaCardsIndex (live trade ideas view)', () => {
  it('lists only live ideas and omits closed ones', () => {
    const html = render();
    expect(html).toContain('Live trade ideas');
    expect(html).toContain('USD/JPY');
    expect(html).not.toContain('EUR/USD');
    expect(html).toContain('1 idea');
  });
});
