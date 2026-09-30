import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import type { TableRow } from '@/lib/database.types';
import { BookAttribution, DecompositionTable } from './BookAttribution';

type Row = TableRow<'position_attribution'>;

const row = (over: Partial<Row>): Row => ({
  id: over.ticker ?? 'x',
  date: '2026-09-29',
  ticker: 'NVDA',
  sector_bucket: null,
  weight_pct: 20,
  position_return_pct: 5,
  benchmark_return_pct: 2,
  contribution_pct: 1,
  selection_effect_pct: 0.6,
  allocation_effect_pct: null,
  total_attribution_pct: 0.6,
  metrics_as_of: null,
  created_at: null,
  window_start_date: '2026-08-29',
  window_end_date: '2026-09-29',
  ...over,
});

const render = (rows: Row[]) => renderToStaticMarkup(createElement(BookAttribution, { rows }));

describe('BookAttribution', () => {
  it('keeps the decomposition table behind its disclosure', () => {
    const html = render([row({})]);
    expect(html).toContain('Decomposition table');
    expect(html).not.toContain('data-testid="book-attribution-table"');
  });

  it('renders the empty state without rows', () => {
    const html = render([]);
    expect(html).toContain('data-testid="book-attribution"');
    expect(html).toContain('No current-book lookback rows yet');
    expect(html).not.toContain('data-testid="attribution-bridge"');
  });

  it('labels itself a lookback diagnostic with the stored window', () => {
    const html = render([row({})]);
    expect(html).toContain('Current-book lookback diagnostic — not realized daily contribution');
    expect(html).toContain('2026-08-29 to 2026-09-29');
  });

  it('decomposes on the kit table with a row header per holding and dashes for gaps', () => {
    const html = renderToStaticMarkup(
      createElement(DecompositionTable, {
        rows: [
          row({ ticker: 'NVDA' }),
          row({
            ticker: 'CASH',
            weight_pct: 10,
            position_return_pct: null,
            contribution_pct: null,
            selection_effect_pct: null,
            allocation_effect_pct: -0.2,
            total_attribution_pct: -0.2,
          }),
        ],
      }),
    );
    expect(html).toContain('data-testid="book-attribution-table"');
    expect(html).toContain('data-slot="table"');
    expect(html).toContain('data-density="compact"');
    expect(html).toMatch(/<th[^>]*data-slot="table-row-header"[^>]*scope="row"[^>]*>NVDA<\/th>/);
    expect(html).toContain('>+0.60%<');
    expect(html).toContain('>-0.20%<');
    expect(html).toContain('>—<');
  });

  it('flags unpriced holdings instead of silently under-counting', () => {
    const html = render([row({}), row({ ticker: 'EWT', total_attribution_pct: null })]);
    expect(html).toContain('data-testid="book-attribution-unpriced"');
    expect(html).toContain('1 of 2 holdings have no priced lookback window');
  });

  it('says why there is no bridge when no benchmark return is stored', () => {
    const html = render([row({ benchmark_return_pct: null })]);
    expect(html).not.toContain('data-testid="attribution-bridge"');
    expect(html).toContain('No benchmark return stored for this window');
  });
});
