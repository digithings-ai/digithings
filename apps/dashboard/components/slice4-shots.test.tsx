// TEMPORARY screenshot harness for Q3b slice 4 — deleted before landing.
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { readdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import AttributionTab from './observability/AttributionTab';
import { PerformanceTearsheetView } from './tearsheet/DashboardTearsheetView';
import type { TableRow } from '@/lib/database.types';
import type { PerformanceTearsheet } from './tearsheet/types';

type AttributionRow = TableRow<'position_attribution'>;

function makeRow(ticker: string, contribution: number | null): AttributionRow {
  return {
    id: `${ticker}-1`,
    date: '2026-08-03',
    ticker,
    sector_bucket: 'Technology',
    weight_pct: 10,
    position_return_pct: 2.0,
    benchmark_return_pct: 1.0,
    contribution_pct: contribution,
    selection_effect_pct: 0.1,
    allocation_effect_pct: null,
    total_attribution_pct: 0.3,
    metrics_as_of: '2026-08-03',
    created_at: '2026-08-03T12:00:00Z',
  };
}

const perfSample: PerformanceTearsheet = {
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
  historicalHoldings: [],
};

function shell(body: string): string {
  const cssDir = join(__dirname, '..', 'out', '_next', 'static', 'css');
  const links = readdirSync(cssDir)
    .filter((f) => f.endsWith('.css'))
    .map((f) => `<link rel="stylesheet" href="/dashboard/_next/static/css/${f}">`)
    .join('\n');
  return `<!DOCTYPE html><html lang="en" data-theme="dark"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">${links}</head><body><div style="max-width:1100px;margin:0 auto;padding:24px">${body}</div></body></html>`;
}

describe('slice4 screenshot harness', () => {
  it('writes fixture pages', () => {
    const attr = renderToStaticMarkup(
      createElement(AttributionTab, {
        attribution: [makeRow('AAPL', 0.42), makeRow('MSFT', -0.31), makeRow('NVDA', 0.18)],
        date: '2026-08-03',
      })
    );
    const perf = renderToStaticMarkup(
      createElement(PerformanceTearsheetView, { data: perfSample, ssot: null })
    );
    const outDir = join(__dirname, '..', 'out');
    writeFileSync(join(outDir, 'slice4-attr.html'), shell(attr));
    writeFileSync(join(outDir, 'slice4-perf.html'), shell(perf));
    expect(attr).toContain('AAPL');
    expect(perf).toContain('Portfolio return');
  });
});
