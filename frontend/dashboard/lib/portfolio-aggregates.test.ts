import { describe, expect, it } from 'vitest';
import { buildSleeveStackSeries, categoryStackLabel } from './portfolio-aggregates';
import { inferPortfolioCategory } from './portfolio-categories';
import type { PositionHistoryRow } from './types';

describe('portfolio category aggregation', () => {
  it('infers deterministic categories for common ETFs', () => {
    expect(inferPortfolioCategory('SHY', null)).toBe('fixed_income_short');
    expect(inferPortfolioCategory('XLK', '—')).toBe('equity_sector');
    expect(inferPortfolioCategory('MYSTERY', null)).toBe('uncategorized');
  });

  it('builds a visible category sleeve when history has sparse categories', () => {
    const rows: PositionHistoryRow[] = [
      { date: '2026-06-17', ticker: 'SHY', weight_pct: 35, category: null, thesis_id: 'defense' },
      { date: '2026-06-17', ticker: 'XLK', weight_pct: 15, category: '—', thesis_id: 'growth' },
      { date: '2026-06-18', ticker: 'SHY', weight_pct: 30, category: null, thesis_id: 'defense' },
      { date: '2026-06-18', ticker: 'ABC', weight_pct: 5, category: null, thesis_id: null },
    ];

    const { data, keys } = buildSleeveStackSeries(rows, 'category');

    expect(keys).toContain('fixed_income_short');
    expect(keys).toContain('equity_sector');
    expect(keys).toContain('uncategorized');
    expect(data[0].fixed_income_short).toBe(35);
    expect(categoryStackLabel('uncategorized')).toBe('Uncategorized');
  });
});
