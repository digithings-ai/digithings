import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

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
  it('renders the short flow strip + levels + scope story, without data', () => {
    const html = renderTab();
    expect(html).toContain('data-testid="twelvex-how-it-works"');
    expect(html).toContain('data-testid="hiw-flow"');
    expect(html).toContain('data-testid="hiw-levels"');
    expect(html).toContain('data-testid="hiw-scope"');
    for (const step of [
      'Calendar',
      'Ingest desk research',
      'Score relevance',
      'Digest',
      'Synthesize ideas',
      'Attach levels',
      'Daily board',
    ]) {
      expect(html).toContain(step);
    }
  });

  it('explains the level stack in trader terms with provenance chips', () => {
    const html = renderTab();
    expect(html).toContain('How entry / stop / targets are set');
    expect(html).toContain('never blank the bracket');
    expect(html).toContain('minimum R:R');
    for (const chip of [
      'broker',
      'bank trade',
      'seasonality',
      'position book',
      'retail book',
      'computed',
      'technical',
      'model',
    ]) {
      expect(html).toContain(chip);
    }
  });

  it('states what the tool is and is not — no execution, no directives', () => {
    const html = renderTab();
    expect(html).toContain('What this is / isn');
    expect(html).toContain('never executes trades');
    expect(html).toContain('display filter only');
    expect(html).toContain('not wired yet');
    expect(html).toContain('source chain');
  });

  it('dropped the old essay structure — no stages, scale, freshness, or tiers', () => {
    const html = renderTab();
    expect(html).not.toContain('data-testid="hiw-scale"');
    expect(html).not.toContain('data-testid="hiw-provenance"');
    expect(html).not.toContain('six stages');
    expect(html).not.toContain('Freshness');
    expect(html).not.toContain('Tier 1');
    expect(html).not.toContain('fx_research_history');
    expect(html).not.toContain('fx_trade_ideas_snapshot');
  });

  it('follows the flat dashboard grammar — no glass, no main, no P&L tokens', () => {
    const html = renderTab();
    expect(html).toContain('border-hair');
    expect(html).not.toContain('glass-card');
    expect(html).not.toContain('rounded-lg');
    expect(html).not.toContain('<main');
    expect(html).not.toContain('text-up');
    expect(html).not.toContain('text-down');
  });
});

describe('TwelveXHeading', () => {
  it('is hook-free, off-screen heading content the Suspense fallback can prerender', () => {
    const html = renderToStaticMarkup(createElement(TwelveXHeading));
    expect(html).toContain('<h1');
    expect(html).toContain('sr-only');
    expect(html).toContain('FX Hub');
    expect(html).not.toContain('<main');
  });
});
