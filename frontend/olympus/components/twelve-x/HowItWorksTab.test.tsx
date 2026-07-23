import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

import { LEAN_BAND, STRONG_BAND } from '@/lib/twelve-x/consensus-bar';
import HowItWorksTab from './HowItWorksTab';
import TwelveXHeading from './TwelveXHeading';
import { TwelveXProvider } from './context';

const noopWatchlist = {
  tickers: [] as string[],
  has: () => false,
  toggle: vi.fn(),
};

function renderTab(): string {
  return renderToStaticMarkup(
    createElement(
      TwelveXProvider,
      {
        value: {
          runDate: null,
          crossLink: vi.fn(),
          openBrief: vi.fn(),
          // Structural stub — the explainer never touches the watchlist.
          watchlist: noopWatchlist as never,
        },
        children: createElement(HowItWorksTab),
      } as never,
    ),
  );
}

describe('HowItWorksTab', () => {
  it('renders the full six-stage pipeline story with its store names, without data', () => {
    const html = renderTab();
    expect(html).toContain('data-testid="twelvex-how-it-works"');
    for (const title of [
      'Ingest desk research',
      'Score relevance',
      'Build consensus',
      'Find confluence',
      'Write the digest',
      'Rank trade ideas',
    ]) {
      expect(html).toContain(title);
    }
    for (const store of [
      'fx_research_history',
      'fx_relevance_ledger',
      'fx_consensus_snapshot',
      'fx_confluence_snapshot',
      'fx_daily_digest',
      'fx_trade_ideas_snapshot',
      'economic_calendar',
    ]) {
      expect(html).toContain(store);
    }
  });

  it('draws the consensus scale from the real band constants', () => {
    const html = renderTab();
    expect(html).toContain('data-testid="hiw-scale"');
    expect(html).toContain(`+${STRONG_BAND}`);
    expect(html).toContain(`+${LEAN_BAND}`);
  });

  it('explains provenance as three tiers ending at named desk reports', () => {
    const html = renderTab();
    expect(html).toContain('data-testid="hiw-provenance"');
    expect(html).toContain('Tier 1');
    expect(html).toContain('Tier 2');
    expect(html).toContain('Tier 3');
    expect(html).toContain('never executes');
  });

  it('follows the flat dashboard grammar — no glass, no main, no P&L tokens', () => {
    const html = renderTab();
    expect(html).toContain('border-hair');
    expect(html).not.toContain('glass-card');
    expect(html).not.toContain('<main');
    expect(html).not.toContain('text-up');
    expect(html).not.toContain('text-down');
  });
});

describe('TwelveXHeading', () => {
  it('is hook-free heading content the Suspense fallback can prerender', () => {
    const html = renderToStaticMarkup(createElement(TwelveXHeading));
    expect(html).toContain('<h1');
    expect(html).toContain('FX Research');
    expect(html).not.toContain('<main');
  });
});
