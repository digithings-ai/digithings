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
function render(
  attribution: AttributionRow[],
  date: string | null = '2026-06-17',
  embedded = false,
): string {
  return renderToStaticMarkup(createElement(AttributionTab, { attribution, date, embedded }));
}

describe('AttributionTab — empty state', () => {
  it('renders the empty state when no rows are provided', () => {
    const html = render([]);
    expect(html).toContain('No current-book lookback rows yet');
  });
});

describe('AttributionTab — CASH drag in active return', () => {
  /**
   * Portfolio: AAPL (+2.00 total), MSFT (+1.00 total), CASH (-0.50 total).
  * activeReturn must include CASH drag: 2.00 + 1.00 - 0.50 = +2.50.
  * portfolioReturn = activeReturn + benchmarkReturn = 2.50 + 1.00 = +3.50.
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

  it('activeReturn includes the CASH row total_attribution_pct', () => {
    const html = render(rows);
    expect(html).toContain('+2.50%');
    expect(html).not.toContain('+3.00%');
  });

  it('portfolioReturn = activeReturn + benchmarkReturn with CASH drag', () => {
    const html = render(rows);
    expect(html).toContain('+3.50%');
    expect(html).not.toContain('+4.00%');
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

  it('uses flat sections when embedded without changing the default card presentation', () => {
    // Wave-2: the box is the kit Card. Flat mode neutralizes its frame with
    // call-site utilities (bg-transparent ring-0), so `bg-card` only appears
    // on the default presentation.
    expect(render(rows)).toContain('data-slot="card"');
    expect(render(rows)).toContain('bg-card');
    expect(render(rows, '2026-06-17', true)).not.toContain('bg-card');
    expect(render(rows)).not.toContain('glass-card');
  });
});

describe('AttributionTab — contribution bars on the kit primitive (Q3b slice 4)', () => {
  const rows: AttributionRow[] = [
    makeRow('AAPL', { contribution_pct: 0.2 }),
    makeRow('MSFT', { contribution_pct: -0.15 }),
    makeRow('CASH', { contribution_pct: 0, sector_bucket: null }),
  ];

  it('renders one labelled, sign-toned bar per priced holding', () => {
    const html = render(rows);
    expect(html).toContain('>AAPL</text>');
    expect(html).toContain('>MSFT</text>');
    expect(html).toContain('<title>AAPL: +0.20%</title>');
    expect(html).toContain('<title>MSFT: -0.15%</title>');
    expect(html).toContain('ts-tone-up');
    expect(html).toContain('ts-tone-down');
  });

  it('keeps the synthetic CASH row out of the by-position chart', () => {
    const html = render(rows);
    expect(html).not.toContain('>CASH</text>');
  });

  it('renders no recharts remnants', () => {
    const html = render(rows);
    expect(html).not.toContain('recharts-wrapper');
  });

  it('keeps the honest empty when nothing is priced', () => {
    const html = render([
      makeRow('AAPL', { contribution_pct: null }),
    ]);
    expect(html).toContain('No priced contributions to chart.');
    expect(html).not.toContain('<title>AAPL:');
  });
});
