/**
 * Tests for the §6.2 allocations builder: envelope scaling plus the folded
 * valuation precedence (stored → derived → market fill → null), mirroring
 * the client lanes in `live-valuation.ts` and `apps/dashboard/README.md`.
 */
import { describe, it, expect } from 'vitest';
import { buildAllocationsData, resolveRowValuation } from './allocations';
import type { AllocationPositionInput } from './allocations';

const base: AllocationPositionInput = {
  ticker: 'DBO',
  weightActual: 5.0031,
  entryPrice: 22.14,
  currentPrice: null,
  unrealizedPnlPct: null,
  sinceEntryReturnPct: null,
  metricsAsOf: null,
};

describe('resolveRowValuation precedence', () => {
  it('prefers the stored unrealized record over recomputing', () => {
    const v = resolveRowValuation({
      ...base,
      currentPrice: 24,
      unrealizedPnlPct: 8.0,
      metricsAsOf: '2026-09-23',
    });
    expect(v.unrealizedPct).toBe(8.0);
    expect(v.marks).toBe('stored');
    expect(v.marksAsOf).toBe('2026-09-23');
  });

  it('accepts since_entry_return_pct as the stored leg', () => {
    const v = resolveRowValuation({
      ...base,
      currentPrice: 24,
      sinceEntryReturnPct: 7.5,
      metricsAsOf: '2026-09-23',
    });
    expect(v.unrealizedPct).toBe(7.5);
    expect(v.marks).toBe('stored');
  });

  it('derives from entry vs close when the record has no number', () => {
    const v = resolveRowValuation({
      ...base,
      currentPrice: 24.354,
      metricsAsOf: '2026-09-23',
    });
    expect(v.unrealizedPct).toBeCloseTo(((24.354 - 22.14) / 22.14) * 100, 6);
    expect(v.marks).toBe('stored');
  });

  it('fills an unstamped mark from the market close (R2-API-only)', () => {
    const v = resolveRowValuation(
      { ...base },
      { price: 23.0, asOf: '2026-09-24' },
    );
    expect(v.currentPrice).toBe(23.0);
    expect(v.unrealizedPct).toBeCloseTo(((23.0 - 22.14) / 22.14) * 100, 6);
    expect(v.marks).toBe('market_api');
    expect(v.marksAsOf).toBe('2026-09-24');
  });

  it('fails closed without basis or mark (empty market fill)', () => {
    const v = resolveRowValuation({ ...base });
    expect(v.unrealizedPct).toBeNull();
    expect(v.currentPrice).toBeNull();
    expect(v.marks).toBe('unavailable');

    const noBasis = resolveRowValuation({
      ...base,
      entryPrice: null,
      currentPrice: 24,
      metricsAsOf: '2026-09-23',
    });
    expect(noBasis.unrealizedPct).toBeNull();
    expect(noBasis.marks).toBe('unavailable');
  });
});

describe('buildAllocationsData (§6.2)', () => {
  const rows: AllocationPositionInput[] = [
    { ...base, ticker: 'DBO', weightActual: 5.0031 },
    {
      ...base,
      ticker: 'EWZ',
      weightActual: 10,
      currentPrice: 30,
      unrealizedPnlPct: 5,
      metricsAsOf: '2026-09-23',
    },
    { ...base, ticker: 'CASH', weightActual: 64.87 },
  ];

  it('scales rows into the §6.1 envelope and excludes CASH', () => {
    const data = buildAllocationsData({ positions: rows, resolvedInvestedPct: 35.13 });
    expect(data.investedPct).toBeCloseTo(35.13, 4);
    expect(data.cashPct).toBeCloseTo(64.87, 4);
    expect(data.rows.map((r) => r.ticker)).toEqual(['DBO', 'EWZ']);
    const scaled = data.rows.reduce((s, r) => s + r.scaledWeightPct, 0);
    expect(scaled).toBeCloseTo(35.13, 3);
  });

  it('marks the book unstamped when any row lacks metrics_as_of', () => {
    const data = buildAllocationsData({ positions: rows, resolvedInvestedPct: 35.13 });
    expect(data.marksUnstamped).toBe(true);
  });

  it('marks the book stamped only when every row carries metrics_as_of', () => {
    const stamped = rows.map((r) => ({ ...r, metricsAsOf: '2026-09-23' }));
    const data = buildAllocationsData({ positions: stamped, resolvedInvestedPct: 35.13 });
    expect(data.marksUnstamped).toBe(false);
  });

  it('fills unstamped rows from market closes without touching weights', () => {
    const data = buildAllocationsData({
      positions: rows,
      resolvedInvestedPct: 35.13,
      marketCloses: new Map([['DBO', { price: 23.0, asOf: '2026-09-24' }]]),
    });
    const dbo = data.rows.find((r) => r.ticker === 'DBO')!;
    expect(dbo.marks).toBe('market_api');
    expect(dbo.unrealizedPct).toBeCloseTo(((23 - 22.14) / 22.14) * 100, 6);
    // Weights come from the envelope only — NULL marks never move them.
    const scaled = data.rows.reduce((s, r) => s + r.scaledWeightPct, 0);
    expect(scaled).toBeCloseTo(35.13, 3);
  });

  it('dedupes double-counted tickers keeping the max weight', () => {
    const data = buildAllocationsData({
      positions: [
        { ...base, ticker: 'EWT', weightActual: 50 },
        { ...base, ticker: 'EWT', weightActual: 50 },
        { ...base, ticker: 'IJR', weightActual: 50 },
      ],
      resolvedInvestedPct: 75,
    });
    expect(data.rows.map((r) => r.ticker)).toEqual(['EWT', 'IJR']);
    expect(data.rows.find((r) => r.ticker === 'EWT')!.scaledWeightPct).toBeCloseTo(
      37.5,
      3,
    );
  });

  it('falls back to the held sum when no invested source resolved', () => {
    const data = buildAllocationsData({
      positions: [{ ...base, ticker: 'DBO', weightActual: 5.0031 }],
      resolvedInvestedPct: null,
    });
    expect(data.investedPct).toBeCloseTo(5.0031, 4);
    expect(data.cashPct).toBeCloseTo(94.9969, 4);
  });
});
