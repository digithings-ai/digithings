/**
 * Parity tests vs `apps/dashboard/lib/book-reconciliation.test.ts` (client).
 * Same fixtures, same expectations, adapted to the worker input shape
 * (`weightActual` for `weight_actual`).
 */
import { describe, it, expect } from 'vitest';
import { isCashTicker, reconcileBook, heldByWeight } from './book';
import type { BookPositionInput } from './book';

const pos = (
  ticker: string,
  weightActual: number,
  weightDelta?: number,
): BookPositionInput => ({
  ticker,
  weightActual,
  weightDelta,
});

describe('reconcileBook (server port of client F3)', () => {
  it('dedupes a ticker double-counted across buckets, normalizes to investedPct', () => {
    const positions = [pos('EWT', 50), pos('EWT', 50), pos('IJR', 50)];
    const { rows, investedPct, cashPct } = reconcileBook(positions, { investedPct: 75 });
    expect(rows.map((r) => r.ticker)).toEqual(['EWT', 'IJR']);
    expect(rows.find((r) => r.ticker === 'EWT')!.scaledWeightPct).toBeCloseTo(37.5, 3);
    expect(investedPct).toBe(75);
    expect(cashPct).toBe(25);
    const sum = rows.reduce((s, r) => s + r.scaledWeightPct, 0) + cashPct;
    expect(sum).toBeCloseTo(100, 3);
  });

  it('falls back to the deduped held sum (capped 100) when investedPct is absent', () => {
    const { investedPct, cashPct } = reconcileBook([pos('EWT', 40), pos('IJR', 40)]);
    expect(investedPct).toBe(80);
    expect(cashPct).toBe(20);
  });

  it('never reports a >100% book even on a raw 150% input', () => {
    const { investedPct, cashPct } = reconcileBook([pos('A', 60), pos('B', 60), pos('C', 30)]);
    expect(investedPct).toBeLessThanOrEqual(100);
    expect(cashPct).toBeGreaterThanOrEqual(0);
    expect(investedPct + cashPct).toBeCloseTo(100, 3);
  });

  it('excludes an explicit CASH row — no double-discount (#1553)', () => {
    const positions = [pos('UUP', 40), pos('TLT', 35), pos('IJR', 15), pos('CASH', 10)];
    const { rows, investedPct, cashPct } = reconcileBook(positions, { investedPct: 90 });
    expect(rows.map((r) => r.ticker)).toEqual(['UUP', 'TLT', 'IJR']);
    expect(rows.find((r) => r.ticker === 'UUP')!.scaledWeightPct).toBeCloseTo(40, 3);
    expect(investedPct).toBe(90);
    expect(cashPct).toBe(10);
    const book = rows.reduce((s, r) => s + r.scaledWeightPct, 0) + cashPct;
    expect(book).toBeCloseTo(100, 3);
  });

  it('carries weight_delta into the scaled basis', () => {
    const { rows } = reconcileBook([pos('EWT', 60, 4), pos('IJR', 40)], {
      investedPct: 75,
    });
    expect(rows.find((r) => r.ticker === 'EWT')!.scaledDelta).toBeCloseTo(3, 3);
    expect(rows.find((r) => r.ticker === 'IJR')!.scaledDelta).toBeNull();
  });

  it('heldByWeight sorts heaviest-first and drops CASH', () => {
    const { rows } = reconcileBook(
      [pos('IJR', 10), pos('UUP', 40), pos('CASH', 10), pos('XLE', 5)],
      { investedPct: 90 },
    );
    expect(heldByWeight(rows).map((r) => r.ticker)).toEqual(['UUP', 'IJR', 'XLE']);
  });

  it('keeps the max-weight duplicate (not first or sum)', () => {
    const { rows } = reconcileBook([pos('EWT', 20), pos('EWT', 55), pos('IJR', 10)], {
      investedPct: 65,
    });
    expect(rows.find((r) => r.ticker === 'EWT')!.weightPct).toBe(55);
  });
});

describe('isCashTicker', () => {
  it('treats trimmed case-insensitive CASH as the synthetic sleeve', () => {
    expect(isCashTicker('CASH')).toBe(true);
    expect(isCashTicker(' cash ')).toBe(true);
    expect(isCashTicker('SPY')).toBe(false);
  });
});
