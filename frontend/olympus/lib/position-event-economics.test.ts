import { describe, expect, it } from 'vitest';
import {
  averageEntryAsOf,
  ledgerEventEconomics,
  realizedReturnVsAverageEntry,
  soldWeightPct,
} from './position-event-economics';

describe('position-event-economics', () => {
  const marks = [
    { date: '2026-06-01', ticker: 'GLD', entry_price: 180 },
    { date: '2026-07-01', ticker: 'GLD', entry_price: 185 },
    { date: '2026-07-15', ticker: 'GLD', entry_price: 190 },
  ];

  it('picks the latest entry on or before the event date', () => {
    expect(averageEntryAsOf(marks, 'GLD', '2026-06-15')).toBe(180);
    expect(averageEntryAsOf(marks, 'GLD', '2026-07-01')).toBe(185);
    expect(averageEntryAsOf(marks, 'gld', '2026-08-01')).toBe(190);
    expect(averageEntryAsOf(marks, 'GLD', '2026-05-01')).toBeNull();
  });

  it('computes sold weight from prev − residual', () => {
    expect(
      soldWeightPct({ event: 'TRIM', prev_weight_pct: 10, weight_pct: 5, price: 200 })
    ).toBe(5);
    expect(
      soldWeightPct({ event: 'EXIT', prev_weight_pct: 8, weight_pct: 0, price: 200 })
    ).toBe(8);
    expect(
      soldWeightPct({ event: 'EXIT', prev_weight_pct: 8, weight_pct: null, price: 200 })
    ).toBe(8);
    expect(
      soldWeightPct({ event: 'TRIM', prev_weight_pct: null, weight_pct: 5, price: 200 })
    ).toBeNull();
  });

  it('fails closed on realized without fill or entry', () => {
    expect(realizedReturnVsAverageEntry(null, 100)).toBeNull();
    expect(realizedReturnVsAverageEntry(110, null)).toBeNull();
    expect(realizedReturnVsAverageEntry(110, 100)).toBeCloseTo(10, 5);
  });

  it('enriches a ~5% gold trim with avg entry, fill, sold wt, and realized %', () => {
    const economics = ledgerEventEconomics(
      {
        date: '2026-08-20',
        ticker: 'GLD',
        event: 'TRIM',
        prev_weight_pct: 10,
        weight_pct: 5,
        price: 199.5,
      },
      marks
    );
    expect(economics.avgEntryPrice).toBe(190);
    expect(economics.fillPrice).toBe(199.5);
    expect(economics.soldWeightPct).toBe(5);
    expect(economics.realizedReturnPct).toBeCloseTo((199.5 / 190 - 1) * 100, 5);
  });

  it('does not invent realized for OPEN/ADD', () => {
    const economics = ledgerEventEconomics(
      {
        date: '2026-06-01',
        ticker: 'GLD',
        event: 'OPEN',
        prev_weight_pct: 0,
        weight_pct: 10,
        price: 180,
      },
      marks
    );
    expect(economics.avgEntryPrice).toBe(180);
    expect(economics.fillPrice).toBe(180);
    expect(economics.soldWeightPct).toBeNull();
    expect(economics.realizedReturnPct).toBeNull();
  });
});
