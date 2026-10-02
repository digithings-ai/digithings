import { describe, expect, it } from 'vitest';
import { deriveBookMovers } from './movers';

describe('deriveBookMovers', () => {
  it('renders a missing mark as null and still sorts the names that have a day', () => {
    const movers = deriveBookMovers(
      [
        { ticker: 'TLT', currentPrice: 88 },
        { ticker: 'dbc', currentPrice: null },
        { ticker: 'XLE', currentPrice: 90 },
        { ticker: 'CASH', currentPrice: 1, isCash: true },
      ],
      [
        { date: '2026-09-29', ticker: 'TLT', close: 87 },
        { date: '2026-09-30', ticker: 'TLT', close: 88 },
        { date: '2026-09-29', ticker: 'XLE', close: 100 },
        { date: '2026-09-30', ticker: 'XLE', close: 95 },
      ],
    );

    expect(movers.map((row) => row.ticker)).toEqual(['XLE', 'TLT', 'DBC']);
    expect(movers[0]).toMatchObject({ mark: 90, dayPct: -10 });
    expect(movers[2]).toEqual({ ticker: 'DBC', mark: null, dayPct: null });
    expect(movers.some((row) => row.dayPct === 0 && row.mark == null)).toBe(false);
  });

  it('does not invent a day when the mark exists but there is no prior close', () => {
    const movers = deriveBookMovers([{ ticker: 'GLD', currentPrice: 245.3 }], []);
    expect(movers).toEqual([{ ticker: 'GLD', mark: 245.3, dayPct: null }]);
  });
});
