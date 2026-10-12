import { afterEach, describe, expect, it, vi } from 'vitest';
import { MISSING_MARK, deriveBookMovers, deriveMovers, loadMovers } from './movers';

const CLOSES = [
  { date: '2026-09-23', ticker: 'SPY', close: 100 },
  { date: '2026-09-24', ticker: 'SPY', close: 110 },
  { date: '2026-09-23', ticker: 'TLT', close: 90 },
  { date: '2026-09-24', ticker: 'TLT', close: 81 },
  { date: '2026-09-23', ticker: 'DBC', close: 20 },
  { date: '2026-09-24', ticker: 'DBC', close: 22 },
];

describe('deriveMovers', () => {
  it('renders an em dash for a missing mark and still sorts the others', () => {
    const movers = deriveMovers(
      [
        { ticker: 'DBC', current_price: null, marks: 'unavailable' },
        { ticker: 'SPY', current_price: 110, marks: 'stored' },
        { ticker: 'TLT', current_price: 81, marks: 'stored' },
        { ticker: 'CASH', current_price: 1, marks: 'stored' },
      ],
      CLOSES,
    );

    expect(movers.map((row) => row.ticker)).toEqual(['SPY', 'TLT', 'DBC']);
    expect(movers.find((row) => row.ticker === 'DBC')).toEqual({
      ticker: 'DBC',
      dayPct: null,
      display: MISSING_MARK,
    });
    expect(movers.find((row) => row.ticker === 'SPY')?.dayPct).toBeCloseTo(10);
    expect(movers.find((row) => row.ticker === 'TLT')?.dayPct).toBeCloseTo(-10);
    expect(movers.find((row) => row.ticker === 'DBC')?.display).not.toMatch(/0/);
    expect(movers.some((row) => row.dayPct === 0)).toBe(false);
  });

  it('does not invent a percent when the prior close is missing', () => {
    const movers = deriveMovers([{ ticker: 'GLD', current_price: 180, marks: 'market_api' }], [
      { date: '2026-09-24', ticker: 'GLD', close: 180 },
    ]);
    expect(movers).toEqual([{ ticker: 'GLD', dayPct: null, display: MISSING_MARK }]);
  });
});

describe('loadMovers', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    delete process.env.NEXT_PUBLIC_DASHBOARD_API_URL;
    delete process.env.NEXT_PUBLIC_MARKET_DATA_URL;
  });

  it('does not invent a percent when market closes are unavailable', async () => {
    process.env.NEXT_PUBLIC_DASHBOARD_API_URL = 'https://api.test';
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: true,
        json: async () => ({
          data: {
            book_as_of: '2026-09-24',
            rows: [
              { ticker: 'SPY', current_price: 110, marks: 'stored' },
              { ticker: 'DBC', current_price: null, marks: 'unavailable' },
              { ticker: 'CASH', current_price: 1, marks: 'stored' },
            ],
          },
          as_of: '2026-09-24',
          retrieval_pin: null,
          provenance: null,
        }),
      })),
    );

    const movers = await loadMovers({ asOf: '2026-09-24' });
    expect(movers.map((row) => row.ticker)).toEqual(['DBC', 'SPY']);
    expect(movers.every((row) => row.dayPct === null && row.display === MISSING_MARK)).toBe(true);
  });
});

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
