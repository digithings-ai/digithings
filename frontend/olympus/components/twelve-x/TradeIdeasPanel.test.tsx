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

const LEVELS_IDEA: FxTradeIdeaRow = {
  ...IDEAS[0],
  trade_levels: {
    entry_low: {
      value: '1.15',
      provenance: 'computed',
      source_ref: 'computed:vol20@2026-07-31|k=1.5|rr=1.5',
    },
    entry_high: {
      value: '1.16',
      provenance: 'computed',
      source_ref: 'computed:vol20@2026-07-31|k=1.5|rr=1.5',
    },
    stop: {
      value: '1.14',
      provenance: 'computed',
      source_ref: 'computed:vol20@2026-07-31|k=1.5|rr=1.5',
    },
    targets: [{ value: '1.18', provenance: 'broker_quoted', source_ref: 'ING.pdf' }],
    risk_reward: 1.5,
    status: 'partial',
  },
  evidence: [
    {
      source_slug: 'dmx-overview',
      instrument: 'USD/JPY',
      as_of: '2026-08-01T00:00:00Z',
      statement: 'Retail 78% long USD/JPY',
      stance: 'contradicts',
      snapshot_id: '00000000-0000-0000-0000-000000000002',
    },
  ],
};

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

  it('does not show levels/evidence while collapsed', () => {
    const html = render([LEVELS_IDEA, IDEAS[1]]);
    expect(html).not.toContain('ING target');
    expect(html).not.toContain('Retail 78% long');
  });

  it('omits Levels header when trade_levels are empty', () => {
    const html = render(IDEAS);
    expect(html).not.toContain('Levels');
    expect(html).not.toContain('Market evidence');
  });
});
