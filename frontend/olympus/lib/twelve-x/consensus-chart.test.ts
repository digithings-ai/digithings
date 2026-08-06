import { describe, expect, it } from 'vitest';
import { augmentWithStaleSeries } from './consensus-chart';

describe('augmentWithStaleSeries', () => {
  it('emits stale extension when a currency last point precedes global latest', () => {
    // USD has data through 2026-06-22, EUR only through 2026-06-20
    const chartData = [
      { run_date: '2026-06-18', USD: 1.2, EUR: -0.5 },
      { run_date: '2026-06-19', USD: 1.3, EUR: -0.6 },
      { run_date: '2026-06-20', USD: 1.4, EUR: -0.7 },
      { run_date: '2026-06-21', USD: 1.5, EUR: null },
      { run_date: '2026-06-22', USD: 1.6, EUR: null },
    ];

    const result = augmentWithStaleSeries(chartData, ['USD', 'EUR']);

    // USD is current, no stale series
    expect(result[4].USD).toBe(1.6);
    expect(result[4].USD__stale).toBeUndefined();

    // EUR last seen on 2026-06-20, stale extension from that point
    expect(result[2].EUR).toBe(-0.7);
    expect(result[2].EUR__stale).toBe(-0.7);
    expect(result[3].EUR).toBeNull();
    expect(result[3].EUR__stale).toBe(-0.7);
    expect(result[4].EUR).toBeNull();
    expect(result[4].EUR__stale).toBe(-0.7);
  });

  it('does not extend beyond latest chart date', () => {
    const chartData = [
      { run_date: '2026-06-20', USD: 1.0 },
      { run_date: '2026-06-21', USD: 1.1 },
    ];

    const result = augmentWithStaleSeries(chartData, ['USD']);

    // Only two rows, no fabrication beyond
    expect(result).toHaveLength(2);
    expect(result[1].USD).toBe(1.1);
    expect(result[1].USD__stale).toBeUndefined();
  });

  it('handles all currencies current — no stale series emitted', () => {
    const chartData = [
      { run_date: '2026-06-21', USD: 1.0, EUR: -0.5 },
      { run_date: '2026-06-22', USD: 1.1, EUR: -0.6 },
    ];

    const result = augmentWithStaleSeries(chartData, ['USD', 'EUR']);

    expect(result[1].USD).toBe(1.1);
    expect(result[1].EUR).toBe(-0.6);
    expect(result[1].USD__stale).toBeUndefined();
    expect(result[1].EUR__stale).toBeUndefined();
  });

  it('handles empty series', () => {
    const result = augmentWithStaleSeries([], ['USD']);
    expect(result).toEqual([]);
  });

  it('anchors stale series at last finite point, not null', () => {
    const chartData = [
      { run_date: '2026-06-18', EUR: -0.5 },
      { run_date: '2026-06-19', EUR: null },
      { run_date: '2026-06-20', EUR: -0.6 },
      { run_date: '2026-06-21', EUR: null },
      { run_date: '2026-06-22', EUR: null },
    ];

    const result = augmentWithStaleSeries(chartData, ['EUR']);

    // Last finite is at 2026-06-20, stale holds from there
    expect(result[2].EUR).toBe(-0.6);
    expect(result[2].EUR__stale).toBe(-0.6);
    expect(result[3].EUR).toBeNull();
    expect(result[3].EUR__stale).toBe(-0.6);
    expect(result[4].EUR).toBeNull();
    expect(result[4].EUR__stale).toBe(-0.6);
  });
});
