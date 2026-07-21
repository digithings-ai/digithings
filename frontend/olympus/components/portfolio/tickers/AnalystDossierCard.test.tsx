import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, it, expect, vi } from 'vitest';
import AnalystDossierCard from './AnalystDossierCard';
import type { AnalystPayload } from '@/lib/types';

vi.mock('lucide-react', () => ({
  TrendingUp: () => createElement('svg', { 'data-icon': 'trending-up' }),
  TrendingDown: () => createElement('svg', { 'data-icon': 'trending-down' }),
}));

vi.mock('@/components/shared/as-of-badge', () => ({
  AsOfBadge: ({ date }: any) => createElement('span', { 'data-testid': 'as-of-badge' }, date),
}));

const mockPayload: AnalystPayload = {
  ticker: 'XLE',
  stance: 'buy',
  conviction_score: 3,
  thesis: 'Energy scarcity remains the highest-conviction expression.',
  bull_case: 'Supply constraints and geopolitical tensions support pricing power.',
  bear_case: 'Demand destruction from recession or energy transition accelerates.',
  tailwinds: ['OPEC+ discipline', 'Capex restraint'],
  headwinds: ['Regulatory pressure', 'Renewable competition'],
  risks: 'Political intervention could cap prices.',
  technicals: 'Above 200-day MA',
  expectations: 'Q4 earnings beat likely',
  fundamentals: 'P/E 12.5, below historical average',
  price_targets: { base: 102, bull: 115, bear: 88 },
  sources: ['https://example.com/analysis'],
  fingerprint_news_hash: 'test-news-hash',
};

describe('AnalystDossierCard — flat editorial workspace', () => {
  it('renders a flat hairline-led structure, not glass-card', () => {
    const html = renderToStaticMarkup(
      createElement(AnalystDossierCard, { payload: mockPayload, asOf: '2026-07-18' })
    );

    // Should NOT have glass-card class
    expect(html).not.toMatch(/analyst-workspace[^>]*glass-card/);
    // Should have flat editorial structure
    expect(html).toContain('analyst-workspace');
    // Should have hairline borders
    expect(html).toContain('border-');
  });

  it('renders thesis prominently in the main argument section', () => {
    const html = renderToStaticMarkup(
      createElement(AnalystDossierCard, { payload: mockPayload, asOf: '2026-07-18' })
    );

    expect(html).toContain('Energy scarcity remains the highest-conviction expression.');
    expect(html).toContain('Thesis');
  });

  it('structures bull/bear evidence in deliberate columns', () => {
    const html = renderToStaticMarkup(
      createElement(AnalystDossierCard, { payload: mockPayload, asOf: '2026-07-18' })
    );

    expect(html).toContain('Supply constraints and geopolitical tensions');
    expect(html).toContain('Demand destruction from recession');
    // Should have grid structure
    expect(html).toContain('grid');
  });

  it('includes tailwind/headwind evidence with neutral styling', () => {
    const html = renderToStaticMarkup(
      createElement(AnalystDossierCard, { payload: mockPayload, asOf: '2026-07-18' })
    );

    expect(html).toContain('OPEC+ discipline');
    expect(html).toContain('Regulatory pressure');
    expect(html).toContain('trending-up');
    expect(html).toContain('trending-down');
    // Should NOT use text-up or text-down (qualitative factors stay neutral)
    expect(html).not.toMatch(/tailwinds[^>]*text-up/);
    expect(html).not.toMatch(/headwinds[^>]*text-down/);
  });
});
