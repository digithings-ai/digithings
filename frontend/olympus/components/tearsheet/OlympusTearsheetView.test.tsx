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
  benchmarkComparisons: [
    {
      ticker: 'SPY',
      returnPct: 8.25,
      series: [
        { date: '2026-05-01', returnPct: 0 },
        { date: '2026-07-17', returnPct: 8.25 },
      ],
    },
    {
      ticker: 'QQQ',
      returnPct: 10,
      series: [
        { date: '2026-05-01', returnPct: 0 },
        { date: '2026-07-17', returnPct: 10 },
      ],
    },
  ],
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
      disposition: 'EXIT',
      eventId: 'old-exit',
    },
  ],
};

function html(data: OlympusTearsheet = sample) {
  return renderToStaticMarkup(createElement(OlympusTearsheetView, { data }));
}

describe('OlympusTearsheetView', () => {
  it('leads with percentage returns — not the base-100 NAV index', () => {
    const out = html();
    expect(out).not.toContain('>NAV index<');
    expect(out).toContain('Portfolio return');
    expect(out).toContain('Excess return');
    expect(out).toContain('Relative gain');
    expect(out).toContain('12.50%');
    expect(out).toContain('4.25%');
    expect(out).toContain('SPY return');
    expect(out).toContain('8.25%');
    expect(out).toContain('>period<');
    expect(out).toContain('2026-05-01–2026-07-17');
    expect(out).toContain('paper NAV index 112.50');
  });

  it('keeps the benchmark control outside the chart (page-global)', () => {
    const out = html();
    expect(out).toContain('data-testid="global-benchmark-control"');
    expect(out).toContain('aria-label="Comparison benchmark"');
    expect(out).toContain('<option value="SPY" selected="">SPY</option>');
    expect(out).toContain('<option value="QQQ">QQQ</option>');
    // Chart legend shows the selected ticker as a series label, not a second <select>
    const chartStart = out.indexOf('data-testid="portfolio-contribution-chart"');
    const chartBlock = out.slice(chartStart);
    expect(chartBlock).not.toContain('<select');
  });

  it('renders insight band for alpha and information ratio', () => {
    const out = html();
    expect(out).toContain('data-testid="performance-insight-band"');
    expect(out).toContain('>Alpha<');
    expect(out).toContain('Information ratio');
  });

  it('renders one additive contribution and exact portfolio-return chart', () => {
    const out = html();
    expect(out).toContain('data-testid="portfolio-contribution-chart"');
    expect(out).toContain('data-chart-layer="contributions"');
    expect(out).toContain('data-chart-layer="portfolio-return"');
    expect(out).toContain('data-chart-layer="benchmark-return"');
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
    const out = html({
      ...sample,
      currentHoldings: [{ ...sample.currentHoldings[0], category: 'sector-consumer-disc' }],
    });
    expect(out).toContain('AAA');
    expect(out).toContain('Consumer discretionary');
    expect(out).not.toContain('sector-consumer-disc');
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

describe('headline vs realized presentation (#1664)', () => {
  it('uses a compact measurement period and no provenance prose', () => {
    const out = html();
    expect(out).not.toContain('Portfolio return · live');
    expect(out).not.toContain('Active return · live');
    expect(out).toContain('2026-05-01–2026-07-17');
    expect(out).toContain('data-region="stamp"');
    expect(out).not.toContain('persisted metrics');
    expect(out).not.toContain('marks the open book · incl. unrealized');
  });

  it('offers populated benchmark assets with SPY selected by default', () => {
    const out = html();
    expect(out).toContain('aria-label="Comparison benchmark"');
    expect(out).toContain('<option value="SPY" selected="">SPY</option>');
    expect(out).toContain('<option value="QQQ">QQQ</option>');
  });

  it('realized exits summarize below the band in the small mono strip', () => {
    const out = html();
    expect(out).toContain('data-testid="realized-summary"');
    expect(out).toContain('Realized · closed positions');
    expect(out).toContain('win rate');
  });

  it('labels TRIM in the realized summary when closed-tab rows include trims', () => {
    const out = html({
      ...sample,
      historicalHoldings: [
        {
          ticker: 'XLF',
          category: 'Financials',
          weightPct: 5,
          unrealizedReturnPct: null,
          realizedReturnPct: 8,
          attributionDate: '2026-08-26',
          disposition: 'TRIM',
          eventId: 'xlf-trim',
        },
      ],
    });
    // Default tab is open book (SSR); summary strip still reflects realized trims.
    expect(out).toContain('data-testid="realized-summary"');
    expect(out).toContain('1 trim');
    expect(out).toContain('avg +8.00%');
    expect(out).toContain('Closed positions');
  });
});

describe('contribution chart presentation', () => {
  it('contribution chart has no per-asset legend — popup carries the identification', () => {
    const out = html();
    expect(out).toContain('Return contribution');
    expect(out).not.toContain('hover for per-position contributions');
    expect(out).not.toContain('Portfolio attribution');
    expect(out).not.toContain('aria-hidden="true" style="background-color');
  });
});
