/**
 * Tests for the §6.2 allocations builder: envelope scaling plus the folded
 * valuation precedence (stored → derived → market fill → null), mirroring
 * the client lanes in `live-valuation.ts` and `apps/dashboard/README.md`.
 */
import { describe, it, expect } from 'vitest';
import { buildAllocationsData, resolveRowValuation } from './allocations';
import type { AllocationPositionInput } from './allocations';
import { replayLedgerWeights, type LedgerWeightEvent } from './ledger-weights';

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

  // ---- DIG-2803: ledger-anchored weights ---------------------------------
  // Chris's verdict case, verbatim: the 28 Sep book wrote UUP 29.9733 /
  // DBO 4.7194 / XLV 5.0322 with no matching events, while the ledger's
  // 25 Sep rebalance targets 15 / 10 / 10. Anchoring must emit the ledger
  // weights AND re-derive the envelope from them, while preserving the
  // positions value and the drift that explains the difference.

  const chrisBook: AllocationPositionInput[] = [
    { ...base, ticker: 'UUP', weightActual: 29.9733 },
    { ...base, ticker: 'DBO', weightActual: 4.7194 },
    { ...base, ticker: 'XLV', weightActual: 5.0322 },
  ];
  const chrisEvents: LedgerWeightEvent[] = [
    { date: '2026-09-25', ticker: 'UUP', event: 'OPEN', weightPct: 15, prevWeightPct: 10 },
    { date: '2026-09-25', ticker: 'DBO', event: 'OPEN', weightPct: 10, prevWeightPct: 5 },
    { date: '2026-09-25', ticker: 'XLV', event: 'TRIM', weightPct: 10, prevWeightPct: 5 },
  ];
  const chrisState = replayLedgerWeights(chrisEvents, '2026-09-28');

  it('emits the ledger weights and keeps the positions value beside them', () => {
    const data = buildAllocationsData({
      positions: chrisBook,
      resolvedInvestedPct: 83.6,
      ledgerState: chrisState,
    });
    const rows = Object.fromEntries(data.rows.map((r) => [r.ticker, r]));
    expect(rows.UUP.weightPct).toBe(15);
    expect(rows.DBO.weightPct).toBe(10);
    expect(rows.XLV.weightPct).toBe(10);
    expect(rows.UUP.weightSource).toBe('ledger');
    expect(rows.DBO.ledgerWeightPct).toBe(10);
    expect(rows.UUP.weightDriftPp).toBeCloseTo(14.9733, 4);
    expect(rows.DBO.weightDriftPp).toBeCloseTo(-5.2806, 4);
    expect(rows.UUP.positionsWeightPct).toBeCloseTo(29.9733, 4);
    expect(data.weightsReconciled).toBe(3);
    expect(data.weightsDrifted).toBe(3);
    expect(data.ledgerConflicts).toEqual([]);
    expect(data.ledgerAsOf).toBe('2026-09-25');
  });

  it('re-derives the envelope from the ledger weights, not the positions ones', () => {
    // heldSum is 35 on the ledger weights (was 39.7249 on the positions
    // weights), so scale = 83.6 / 35 and DBO lands at 10 * that. Computing
    // the envelope off the positions sum instead is the DIG-2803 defect.
    const data = buildAllocationsData({
      positions: chrisBook,
      resolvedInvestedPct: 83.6,
      ledgerState: chrisState,
    });
    const scale = 83.6 / 35;
    const dbo = data.rows.find((r) => r.ticker === 'DBO')!;
    expect(dbo.scaledWeightPct).toBeCloseTo(10 * scale, 4);
    expect(data.investedPct).toBeCloseTo(83.6, 4);
    expect(data.cashPct).toBeCloseTo(16.4, 4);
  });

  it('is byte-identical to the unanchored build when no ledger is supplied', () => {
    // The fail-closed contract: `ledgerState: null` must reproduce the
    // pre-DIG-2803 output exactly, which is what every existing lane relies on.
    const anchored = buildAllocationsData({
      positions: chrisBook,
      resolvedInvestedPct: 83.6,
      ledgerState: null,
    });
    expect(anchored.rows.map((r) => r.weightPct)).toEqual([29.9733, 4.7194, 5.0322]);
    expect(anchored.rows.every((r) => r.weightSource === 'positions_no_ledger')).toBe(true);
    expect(anchored.rows.every((r) => r.ledgerWeightPct === null)).toBe(true);
    expect(anchored.weightsReconciled).toBe(0);
    expect(anchored.weightsDrifted).toBe(0);
    expect(anchored.ledgerAsOf).toBeNull();
  });

  it('holds the positions weight for a ticker the ledger does not cover', () => {
    const data = buildAllocationsData({
      positions: [{ ...chrisBook[0] }, { ...base, ticker: 'IJR', weightActual: 4 }],
      resolvedInvestedPct: null,
      ledgerState: chrisState,
    });
    const ijr = data.rows.find((r) => r.ticker === 'IJR')!;
    expect(ijr.weightPct).toBe(4);
    expect(ijr.weightSource).toBe('positions');
    expect(ijr.ledgerWeightPct).toBeNull();
    expect(ijr.weightDriftPp).toBeNull();
  });
});
