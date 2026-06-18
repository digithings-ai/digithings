import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import AttributionTab from './AttributionTab';
import type { TableRow } from '@/lib/database.types';

type AttributionRow = TableRow<'position_attribution'>;

function makeRow(
  ticker: string,
  overrides: Partial<AttributionRow> = {},
): AttributionRow {
  return {
    id: `${ticker}-1`,
    date: '2026-06-17',
    ticker,
    sector_bucket: 'Technology',
    weight_pct: 10,
    position_return_pct: 2.0,
    benchmark_return_pct: 1.0,
    contribution_pct: 0.2,
    selection_effect_pct: 0.1,
    allocation_effect_pct: null,
    total_attribution_pct: 0.3,
    metrics_as_of: '2026-06-17',
    created_at: '2026-06-17T12:00:00Z',
    ...overrides,
  };
}

/** Render the component to a static HTML string for text-content assertions. */
function render(attribution: AttributionRow[], date: string | null = '2026-06-17'): string {
  return renderToStaticMarkup(createElement(AttributionTab, { attribution, date }));
}

describe('AttributionTab — empty state', () => {
  it('renders the empty state when no rows are provided', () => {
    const html = render([]);
    expect(html).toContain('No attribution rows yet');
  });
});

describe('AttributionTab — CASH exclusion from active return', () => {
  /**
   * Portfolio: AAPL (+2.00 total), MSFT (+1.00 total), CASH (-0.50 total).
   * activeReturn should be AAPL + MSFT = +3.00, NOT +2.50 (which includes CASH).
   * portfolioReturn = activeReturn + benchmarkReturn = 3.00 + 1.00 = +4.00.
   */
  const rows: AttributionRow[] = [
    makeRow('AAPL', { total_attribution_pct: 2.0, benchmark_return_pct: 1.0 }),
    makeRow('MSFT', { total_attribution_pct: 1.0, benchmark_return_pct: 1.0 }),
    makeRow('CASH', {
      total_attribution_pct: -0.5,
      benchmark_return_pct: null,
      sector_bucket: null,
    }),
  ];

  it('activeReturn excludes the CASH row total_attribution_pct', () => {
    const html = render(rows);
    // activeReturn = 2.0 + 1.0 = 3.00; would be 2.50 if CASH were included
    expect(html).toContain('+3.00%');
    expect(html).not.toContain('+2.50%');
  });

  it('portfolioReturn = activeReturn + benchmarkReturn (CASH excluded)', () => {
    const html = render(rows);
    // portfolioReturn = 3.00 + 1.00 = 4.00; would be 3.50 if CASH were included
    expect(html).toContain('+4.00%');
    expect(html).not.toContain('+3.50%');
  });

  it('holdings count excludes CASH', () => {
    const html = render(rows);
    // holdings = 2 (AAPL, MSFT); would be 3 if CASH were included
    expect(html).toContain('2 holdings');
    expect(html).not.toContain('3 holdings');
  });
});

describe('AttributionTab — activeReturn with only equity rows (no CASH)', () => {
  const rows: AttributionRow[] = [
    makeRow('GOOGL', { total_attribution_pct: 1.5, benchmark_return_pct: 0.5 }),
    makeRow('AMZN', { total_attribution_pct: -0.5, benchmark_return_pct: 0.5 }),
  ];

  it('sums all rows when there is no CASH row', () => {
    const html = render(rows);
    // activeReturn = 1.5 + (-0.5) = 1.00
    expect(html).toContain('+1.00%');
  });

  it('portfolioReturn = activeReturn + benchmarkReturn', () => {
    const html = render(rows);
    // portfolioReturn = 1.00 + 0.50 = 1.50
    expect(html).toContain('+1.50%');
  });
});

describe('AttributionTab — null total_attribution_pct (unpriced)', () => {
  it('shows partial warning when a holding has null total_attribution_pct', () => {
    const rows: AttributionRow[] = [
      makeRow('NVDA', { total_attribution_pct: 2.0, benchmark_return_pct: 1.0 }),
      makeRow('TSLA', { total_attribution_pct: null, benchmark_return_pct: 1.0 }),
    ];
    const html = render(rows);
    expect(html).toContain('partial');
    expect(html).toContain('1 unpriced');
  });

  it('CASH null total_attribution_pct does not inflate unpriced count', () => {
    const rows: AttributionRow[] = [
      makeRow('NVDA', { total_attribution_pct: 1.5, benchmark_return_pct: 1.0 }),
      makeRow('CASH', { total_attribution_pct: null, benchmark_return_pct: null }),
    ];
    const html = render(rows);
    // CASH has null total_attribution_pct but should not appear in unpriced (it's excluded)
    expect(html).not.toContain('unpriced');
    // 1 holding, no partial warning
    expect(html).toContain('1 holding');
    expect(html).not.toContain('1 holdings');
  });
});

describe('AttributionTab — stat tile labels', () => {
  const rows: AttributionRow[] = [
    makeRow('SPY', { total_attribution_pct: 1.0, benchmark_return_pct: 1.0 }),
  ];

  it('renders the date in the As-of tile', () => {
    const html = render(rows, '2026-06-17');
    expect(html).toContain('2026-06-17');
  });

  it('renders benchmark label', () => {
    const html = render(rows);
    expect(html).toContain('Benchmark');
  });

  it('renders Active return label', () => {
    const html = render(rows);
    expect(html).toContain('Active return');
  });
});
