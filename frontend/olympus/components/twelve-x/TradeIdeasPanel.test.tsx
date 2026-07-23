import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

import type { FxTradeIdeaRow } from '@/lib/twelve-x/types';
import TradeIdeasPanel from './TradeIdeasPanel';
import { TwelveXProvider } from './context';

const IDEAS: FxTradeIdeaRow[] = [
  {
    run_date: '2026-07-22',
    rank: 1,
    pair: 'USD/JPY',
    direction: 'short',
    title: 'JPY SHORT — via USD/JPY',
    thesis: 'BoJ normalization path repricing.',
    catalyst: 'BoJ minutes Thursday',
    levels: [],
    citations: [{ broker: 'Desk Alpha', source_file: 'alpha/usdjpy.md' }],
    as_of: '2026-07-22T10:00:00Z',
  },
  {
    run_date: '2026-07-22',
    rank: 2,
    pair: 'EUR/USD',
    direction: 'long',
    title: 'EUR grind higher',
    thesis: 'Rate differential compression.',
    catalyst: 'ECB speakers',
    levels: [],
    citations: [{ source_file: 'beta/eurusd-note.md' }],
    as_of: '2026-07-22T10:00:00Z',
  },
];

function render(ideas: FxTradeIdeaRow[]): string {
  return renderToStaticMarkup(
    createElement(
      TwelveXProvider,
      {
        value: {
          runDate: '2026-07-22',
          crossLink: vi.fn(),
          openBrief: vi.fn(),
          watchlist: { tickers: [], has: () => false, toggle: vi.fn() } as never,
        },
        children: createElement(TradeIdeasPanel, { ideas, confluence: [] }),
      } as never,
    ),
  );
}

describe('TradeIdeasPanel', () => {
  it('renders the focal #1 idea and compact rows for the rest', () => {
    const html = render(IDEAS);
    expect(html).toContain('USD/JPY');
    expect(html).toContain('EUR/USD');
    expect(html).toContain('#1');
    expect(html).toContain('#2');
  });

  it('idea rows expand in place — ideas are run artifacts with no brief to open (#1664)', () => {
    const html = render(IDEAS);
    // Every idea button is a collapsed disclosure, not a brief link.
    expect(html).toContain('aria-expanded="false"');
    // Contributing-desk detail only appears once a row is expanded.
    expect(html).not.toContain('Contributing desks');
  });

  it('keeps direction off the P&L tokens', () => {
    const html = render(IDEAS);
    expect(html).not.toContain('text-up');
    expect(html).not.toContain('text-down');
  });
});
