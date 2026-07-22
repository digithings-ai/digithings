import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { OlympusTearsheetView } from './OlympusTearsheetView';
import type { OlympusTearsheet } from './types';

const sample: OlympusTearsheet = {
  currentNav: 112.5,
  netReturnPct: 12.5,
  benchmarkReturnPct: 8.25,
  relativeReturnPct: 4.25,
  benchmarkTicker: 'SPY',
  returnsSource: 'persisted',
  metricsAsOf: '2026-07-17',
  inceptionDate: '2026-05-01',
  holdingsAsOf: '2026-07-17',
  generatedAt: '2026-07-17T22:00:00Z',
  navSeries: [
    { date: '2026-05-01', nav: 100, returnPct: 0 },
    { date: '2026-07-17', nav: 112.5, returnPct: 12.5 },
  ],
  contributionSeries: [
    { t: '2026-05-01', returnPct: 0, contributions: { AAA: 0 } },
    { t: '2026-07-17', returnPct: 12.5, contributions: { AAA: 1 } },
  ],
  currentHoldings: [
    {
      ticker: 'AAA',
      category: 'Technology',
      weightPct: 20,
      unrealizedReturnPct: 5,
      realizedReturnPct: null,
      attributionDate: '2026-07-17',
    },
  ],
  historicalHoldings: [
    {
      ticker: 'OLD',
      category: 'Industrials',
      weightPct: 10,
      unrealizedReturnPct: null,
      realizedReturnPct: -2,
      attributionDate: '2026-06-20',
    },
  ],
};

function html(data: OlympusTearsheet = sample) {
  return renderToStaticMarkup(createElement(OlympusTearsheetView, { data }));
}

describe('OlympusTearsheetView', () => {
  it('prioritizes NAV, persisted portfolio return, and active return', () => {
    const out = html();
    expect(out).toContain('>NAV<');
    expect(out).toContain('Portfolio return');
    expect(out).toContain('Active return');
    expect(out).toContain('112.50');
    expect(out).toContain('12.50%');
    expect(out).toContain('4.25%');
    expect(out).toContain('persisted metrics');
  });

  it('renders one additive contribution and exact portfolio-return chart', () => {
    const out = html();
    expect(out).toContain('data-testid="portfolio-contribution-chart"');
    expect(out).toContain('data-chart-layer="contributions"');
    expect(out).toContain('data-chart-layer="portfolio-return"');
    expect(out).toContain('data-series="AAA"');
    expect(out).not.toContain('data-testid="portfolio-return-chart"');
    expect(out).not.toContain('data-testid="position-return-chart"');
    expect(out.toLowerCase()).not.toContain('drawdown');
  });

  it('uses an icon-only accessible PDF control', () => {
    const out = html();
    expect(out).toContain('aria-label="Download performance tear sheet as PDF"');
    expect(out).not.toContain('>Download PDF<');
  });

  it('offers open and closed position performance as tabs', () => {
    const out = html();
    expect(out).toContain('Open positions');
    expect(out).toContain('Closed positions');
    expect(out).toContain('role="tablist"');
    expect(out).toContain('role="tabpanel"');
  });

  it('shows current persisted holding performance without decision diagnostics', () => {
    const out = html();
    expect(out).toContain('AAA');
    expect(out).toContain('Unrealized');
    expect(out).not.toContain('Contribution');
    expect(out).not.toContain('hit rate');
    expect(out).not.toContain('mean alpha');
    expect(out).not.toContain('Conviction calibration');
    expect(out).not.toContain('live nav');
  });

  it('keeps every holding row mounted inside the contained table scroll', () => {
    const currentHoldings = Array.from({ length: 11 }, (_, index) => ({
      ...sample.currentHoldings[0],
      ticker: `T${index + 1}`,
    }));
    const out = html({ ...sample, currentHoldings });
    expect(out).toContain('T11');
    expect(out).not.toContain('Showing latest 10 rows');
  });

  it('renders a truthful empty state when persisted metrics are absent', () => {
    const out = html({
      ...sample,
      netReturnPct: null,
      benchmarkReturnPct: null,
      relativeReturnPct: null,
      returnsSource: 'unavailable',
      metricsAsOf: null,
      currentNav: null,
      navSeries: [],
      contributionSeries: [],
      currentHoldings: [],
    });
    expect(out).toContain('awaiting persisted metrics');
    expect(out).toContain('No open position performance is stored yet.');
  });
});
