import { describe, expect, it } from 'vitest';
import type { MatrixCell } from './types';
import { cellValue, convictionWeight, deriveMatrixHeat, matrixHeatSummary } from './matrix-heat';

function cell(
  broker: string,
  column: MatrixCell['column'],
  direction: string,
  conviction = 'high',
): MatrixCell {
  return {
    broker,
    column,
    currency: column,
    direction,
    conviction,
    run_date: '2026-06-22',
    report_date: null,
    source_file: `${broker}-${column}.md`,
  };
}

describe('cellValue', () => {
  it('signs by direction and scales by conviction', () => {
    expect(cellValue({ direction: 'bullish', conviction: 'high' })).toBe(1);
    expect(cellValue({ direction: 'bearish', conviction: 'low' })).toBeCloseTo(-0.33);
    expect(cellValue({ direction: 'watch', conviction: 'high' })).toBe(0);
    expect(cellValue({ direction: 'neutral', conviction: 'medium' })).toBe(0);
    expect(convictionWeight('??')).toBe(0.5);
  });
});

describe('deriveMatrixHeat', () => {
  const cells = [
    cell('Beta', 'USD', 'bullish'),
    cell('Alpha', 'USD', 'bearish', 'medium'),
    cell('Alpha', 'EUR', 'bullish', 'low'),
    cell('Gamma', 'USD', 'bullish', 'low'),
  ];
  const heat = deriveMatrixHeat(cells);

  it('sorts desks alphabetically and keeps the fixed 8 columns', () => {
    expect(heat.brokers).toEqual(['Alpha', 'Beta', 'Gamma']);
    expect(heat.columns).toHaveLength(8);
    expect(heat.columns).not.toContain('NOK');
    expect(heat.columns).not.toContain('SEK');
    expect(heat.values[0]).toHaveLength(8);
  });

  it('puts signed weights in the right cell and null where a desk has no view', () => {
    const usd = heat.columns.indexOf('USD');
    const eur = heat.columns.indexOf('EUR');
    expect(heat.values[0][usd]).toBeCloseTo(-0.66);
    expect(heat.values[0][eur]).toBeCloseTo(0.33);
    expect(heat.values[1][eur]).toBeNull();
  });

  it('builds the crowd marginal and per-desk activity', () => {
    const usd = heat.crowd.find((c) => c.column === 'USD')!;
    expect(usd).toMatchObject({ bull: 2, bear: 1, total: 3 });
    expect(usd.net).toBeCloseTo(1 / 3);
    expect(heat.crowd.find((c) => c.column === 'JPY')?.net).toBeNull();
    expect(heat.activity).toEqual([2, 1, 1]);
  });

  it('summarises for screen readers and handles no data', () => {
    expect(matrixHeatSummary(heat)).toContain('USD 2 bullish 1 bearish of 3');
    expect(deriveMatrixHeat([]).brokers).toEqual([]);
    expect(matrixHeatSummary(deriveMatrixHeat([]))).toContain('no desk views');
  });
});
