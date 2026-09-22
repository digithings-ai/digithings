import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { PerformanceTearsheetView } from './DashboardTearsheetView';
import type { PerformanceTearsheet } from './types';
import type { PerformanceSsotMeta } from '@/lib/performance-ssot';

const sample: PerformanceTearsheet = {
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
        { date: '2026-07-17', returnPct: 0 },
        { date: '2026-08-03', returnPct: 8.25 },
      ],
    },
    {
      ticker: 'QQQ',
      returnPct: 10,
      series: [
        { date: '2026-07-17', returnPct: 0 },
        { date: '2026-08-03', returnPct: 10 },
      ],
    },
  ],
  returnsSource: 'persisted',
  metricsAsOf: '2026-08-03',
  inceptionDate: '2026-07-17',
  holdingsAsOf: '2026-08-03',
  generatedAt: '2026-08-03T22:00:00Z',
  navSeries: [
    { date: '2026-07-17', nav: 100, returnPct: 0 },
    { date: '2026-08-03', nav: 112.5, returnPct: 12.5 },
  ],
  contributionSeries: [
    { t: '2026-07-17', returnPct: 0, contributions: { AAA: 0 } },
    { t: '2026-08-03', returnPct: 12.5, contributions: { AAA: 1 } },
  ],
  currentHoldings: [
    {
      ticker: 'AAA',
      category: 'Technology',
      weightPct: 20,
      unrealizedReturnPct: 5,
      realizedReturnPct: null,
      attributionDate: '2026-08-03',
    },
  ],
  historicalHoldings: [
    {
      ticker: 'OLD',
      category: 'Industrials',
      weightPct: 10,
      unrealizedReturnPct: null,
      realizedReturnPct: -2,
      attributionDate: '2026-07-20',
      disposition: 'EXIT',
      eventId: 'old-exit',
    },
  ],
};

function html(data: PerformanceTearsheet = sample, ssot: PerformanceSsotMeta | null = null) {
  return renderToStaticMarkup(createElement(PerformanceTearsheetView, { data, ssot }));
}

describe('PerformanceTearsheetView', () => {
  it('leads with percentage returns — single excess metric, no relative-gain duplicate', () => {
    const out = html();
    expect(out).not.toContain('>NAV index<');
    expect(out).toContain('Portfolio return');
    expect(out).toContain('Excess return');
    expect(out).not.toContain('Relative gain');
    expect(out).toContain('12.50%');
    expect(out).toContain('4.25%');
    expect(out).toContain('SPY return');
    expect(out).toContain('8.25%');
    expect(out).toContain('>period<');
    expect(out).toContain('2026-07-17–2026-08-03');
    expect(out).not.toContain('paper NAV index 112.50');
  });

  // Q3b slice 4: flat mono register — ledger eyebrow, no display-hero type,
  // no surface fills, no dead print hook. Full fixture renders every band,
  // so each absence would fail if the old markup came back.
  it('keeps the tearsheet chrome in the flat mono register', () => {
    const out = html();
    expect(out).toContain('Portfolio · performance');
    expect(out).not.toContain('text-2xl');
    expect(out).not.toContain('bg-surface/80');
    expect(out).not.toContain('ts-print-root');
    expect(out).not.toContain('font-display text-xl font-normal text-ink">Open positions');
    expect(out).not.toContain('font-display text-xl text-ink">Return contribution');
  });

  it('keeps the benchmark control outside the chart (page-global)', () => {
    // Wave 4: the benchmark picker is the kit `Select` (portal-rendered list), so the
    // old native `<option>` markup is gone. The page-global placement contract is
    // unchanged: the labelled trigger sits in the header, outside the chart section,
    // and the selected asset renders in the trigger value.
    const out = html();
    expect(out).toContain('data-testid="global-benchmark-control"');
    expect(out).toContain('aria-label="Comparison benchmark"');
    expect(out).toContain('data-slot="select-trigger"');
    expect(out).toMatch(/data-slot="select-value"[^>]*>SPY</);
    const chartStart = out.indexOf('data-testid="portfolio-contribution-chart"');
    const chartBlock = out.slice(chartStart);
    expect(chartBlock).not.toContain('aria-label="Comparison benchmark"');
  });

  it('renders insight band for alpha and information ratio', () => {
    const out = html();
    expect(out).toContain('data-testid="performance-insight-band"');
    expect(out).toContain('>Alpha<');
    expect(out).toContain('Information ratio');
    expect(out).toContain('daily excess');
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

  it('shows open positions and routes closed activity to Ledger', () => {
    const out = html();
    expect(out).toContain('Open positions');
    expect(out).toContain('data-testid="open-positions-panel"');
    expect(out).not.toContain('Closed positions');
    expect(out).not.toContain('role="tablist"');
    expect(out).toContain('data-testid="ledger-doorway"');
    expect(out).toContain('data-testid="ledger-doorway-link"');
    expect(out).toContain('href="/portfolio/ledger"');
    expect(out).toContain('1 recorded exit or trim');
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
      historicalHoldings: [],
    });
    expect(out).toContain('awaiting persisted metrics');
    expect(out).toContain('No open position performance is stored yet.');
    expect(out).toContain('No recorded exits or trims');
  });
});

describe('headline vs realized presentation (#1664)', () => {
  it('uses a compact measurement period and no provenance prose', () => {
    const out = html();
    expect(out).not.toContain('Portfolio return · live');
    expect(out).not.toContain('Active return · live');
    expect(out).toContain('2026-07-17–2026-08-03');
    expect(out).toContain('data-region="stamp"');
    expect(out).not.toContain('persisted metrics');
    expect(out).not.toContain('marks the open book · incl. unrealized');
  });

  it('offers populated benchmark assets with SPY selected by default', () => {
    // Wave 4: kit `Select` serves the list through a portal, so the option set is not
    // in static markup; the observable contract is the labelled trigger plus the
    // selected value. The control only renders at all when `benchmarkComparisons` is
    // non-empty, so its presence covers the "populated" half; SPY is the default value.
    const out = html();
    expect(out).toContain('aria-label="Comparison benchmark"');
    expect(out).toContain('data-slot="select-trigger"');
    expect(out).toMatch(/data-slot="select-value"[^>]*>SPY</);
    expect(out).toContain('value="SPY"');
  });

  it('does not duplicate realized fills on the tearsheet — Ledger is SSOT', () => {
    const out = html();
    expect(out).not.toContain('data-testid="realized-summary"');
    expect(out).not.toContain('Realized · closed positions');
    expect(out).toContain('activity lives on Ledger');
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

  it('flags a degraded marks fallback on the contribution chart', () => {
    const out = html({ ...sample, contributionSource: 'marks_degraded' });
    expect(out).toContain('data-testid="contribution-source-note"');
    expect(out).toContain('Finalized attribution unavailable');
  });

  it('flags a truncated realized series without claiming it is unavailable', () => {
    const out = html({ ...sample, contributionSource: 'realized_truncated' });
    expect(out).toContain('data-testid="contribution-source-note"');
    expect(out).toContain('truncated at the read cap');
    expect(out).not.toContain('Finalized attribution unavailable');
  });

  it('keeps the contribution chrome quiet for realized and marks sources', () => {
    for (const source of ['realized', 'marks'] as const) {
      expect(html({ ...sample, contributionSource: source })).not.toContain(
        'data-testid="contribution-source-note"'
      );
    }
  });
});

describe('performance SSOT chrome (#3604)', () => {
  const sampleSsot: PerformanceSsotMeta = {
    navContract: 'legacy_estimate',
    navAsOf: '2026-07-20',
    tipDayReturnPct: 0.1,
    tipInvestedPct: 80,
    tipCashPct: 20,
    metricsAsOf: '2026-07-17',
    metricsLagDays: 3,
    metricsLagging: true,
    bookAsOf: '2026-07-17',
    marksUnstamped: false,
    investedDefinition: 'accounting_nav_tip',
  };

  it('ends the period at the NAV tip, not a lagged metrics stamp', () => {
    const out = html(sample, sampleSsot);
    expect(out).toContain('2026-07-17–2026-07-20');
    expect(out).toContain('nav tip 2026-07-20');
  });

  it('badges NAV-behind-metrics divergence as nav lag', () => {
    const out = html(sample, {
      ...sampleSsot,
      navAsOf: '2026-07-15',
      metricsAsOf: '2026-07-17',
      metricsLagDays: -2,
      metricsLagging: true,
    });
    expect(out).toContain('data-testid="tearsheet-metrics-lag-badge"');
    expect(out).toContain('nav lag');
    expect(out).toContain('2026-07-17');
  });
});
