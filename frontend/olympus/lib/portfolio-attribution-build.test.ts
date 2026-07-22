import { describe, expect, it } from 'vitest';
import type { TableRow } from './database.types';
import { buildPortfolioAttributionData } from './observability-queries';

describe('buildPortfolioAttributionData', () => {
  it('keeps the complete latest attribution snapshot and all decision history', () => {
    const attribution = [
      { id: 'old', date: '2026-06-22', ticker: 'AAPL' },
      { id: 'new-aapl', date: '2026-06-23', ticker: 'AAPL' },
      { id: 'new-nvda', date: '2026-06-23', ticker: 'NVDA' },
    ] as TableRow<'position_attribution'>[];
    const decisions = [
      { id: 'decision-1', ticker: 'AAPL' },
      { id: 'decision-2', ticker: 'NVDA' },
    ] as TableRow<'decision_log'>[];

    const result = buildPortfolioAttributionData({ attribution, decisions });

    expect(result.attributionDate).toBe('2026-06-23');
    expect(result.attribution.map((row) => row.id)).toEqual(['new-aapl', 'new-nvda']);
    expect(result.decisions).toBe(decisions);
  });
});