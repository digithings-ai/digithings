import { describe, expect, it, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { PortfolioTeaserSurface } from './portfolio-teaser-surface';

vi.mock('@/lib/use-entitlement', () => ({
  usePlanTier: () => 'free',
}));

describe('PortfolioTeaserSurface', () => {
  it('renders ticker names for free tier without weights', () => {
    const html = renderToStaticMarkup(
      <PortfolioTeaserSurface tier="free" tickers={['AAPL', 'MSFT', 'CASH']} />,
    );
    expect(html).toContain('data-testid="portfolio-teaser"');
    expect(html).toContain('AAPL');
    expect(html).toContain('MSFT');
    expect(html).not.toContain('%');
  });

  it('hides when baseline+ (full book available)', () => {
    const html = renderToStaticMarkup(
      <PortfolioTeaserSurface tier="baseline" tickers={['AAPL']} />,
    );
    expect(html).toBe('');
  });
});
