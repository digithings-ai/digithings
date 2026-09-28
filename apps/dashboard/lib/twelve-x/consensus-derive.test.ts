import { describe, expect, it } from 'vitest';
import {
  consensusAverageAt,
  consensusAverageSeries,
  latestConsensusAverages,
  selectLatestCompleteConsensus,
} from './consensus-derive';

const G10 = ['USD', 'EUR', 'JPY', 'GBP', 'CHF', 'CAD', 'AUD', 'NZD', 'SEK', 'NOK'];

describe('selectLatestCompleteConsensus', () => {
  it('skips an incrementally published run in favor of the latest complete G10 run', () => {
    const complete = G10.map((currency) => ({ run_date: '2026-07-15', currency }));
    const partial = [{ run_date: '2026-07-16', currency: 'USD' }];

    const selected = selectLatestCompleteConsensus([...complete, ...partial]);

    expect(selected).toHaveLength(10);
    expect(new Set(selected.map((row) => row.run_date))).toEqual(new Set(['2026-07-15']));
    expect(selected.map((row) => row.currency)).toEqual(G10);
  });

  it('returns the newest partial run when no complete run exists', () => {
    const selected = selectLatestCompleteConsensus([
      { run_date: '2026-07-15', currency: 'EUR' },
      { run_date: '2026-07-16', currency: 'USD' },
    ]);

    expect(selected).toEqual([{ run_date: '2026-07-16', currency: 'USD' }]);
  });
});

describe('consensusAverageAt', () => {
  it('returns null for i<0', () => {
    expect(consensusAverageAt([{ score: 1 }], -1)).toBeNull();
  });

  it('returns null for empty series', () => {
    expect(consensusAverageAt([], 0)).toBeNull();
  });

  it('computes a partial mean when fewer than `window` points precede i', () => {
    const series = [{ score: 2 }, { score: 4 }, { score: 6 }];
    // i=2, window 5 → mean of [2,4,6] = 4
    expect(consensusAverageAt(series, 2)).toBe(4);
    // i=0 → just [2]
    expect(consensusAverageAt(series, 0)).toBe(2);
  });

  it('averages exactly `window` points', () => {
    const series = [10, 20, 30, 40, 50].map((score) => ({ score }));
    // i=4, window 5 → mean [10..50] = 30
    expect(consensusAverageAt(series, 4)).toBe(30);
  });

  it('slides the window: only the last `window` points up to i count', () => {
    const series = [0, 0, 0, 0, 0, 100].map((score) => ({ score }));
    // i=5, window 5 → mean of indices 1..5 = [0,0,0,0,100] = 20
    expect(consensusAverageAt(series, 5)).toBe(20);
  });

  it('respects a custom window size', () => {
    const series = [10, 20, 30, 40].map((score) => ({ score }));
    // i=3, window 2 → mean of [30,40] = 35
    expect(consensusAverageAt(series, 3, 2)).toBe(35);
  });

  it('skips non-finite scores and averages only finite points', () => {
    const series = [
      { score: 2 },
      { score: Number.NaN },
      { score: 6 },
      { score: Number.POSITIVE_INFINITY },
    ];
    // i=3, window 5 → finite points [2,6] → mean 4
    expect(consensusAverageAt(series, 3)).toBe(4);
  });

  it('returns null when no finite points are in the window', () => {
    const series = [{ score: Number.NaN }, { score: Number.POSITIVE_INFINITY }];
    expect(consensusAverageAt(series, 1)).toBeNull();
  });
});

describe('consensusAverageSeries', () => {
  it('maps each index to its trailing average', () => {
    const series = [10, 20, 30].map((score) => ({ score }));
    expect(consensusAverageSeries(series)).toEqual([10, 15, 20]);
  });

  it('returns an empty array for an empty series', () => {
    expect(consensusAverageSeries([])).toEqual([]);
  });

  it('respects a custom window', () => {
    const series = [10, 20, 30].map((score) => ({ score }));
    // window 2 → [10, 15, 25]
    expect(consensusAverageSeries(series, 2)).toEqual([10, 15, 25]);
  });
});

describe('latestConsensusAverages', () => {
  it('derives all fields off the last index', () => {
    const series = [10, 20, 30, 40, 50, 60].map((score) => ({ score }));
    const r = latestConsensusAverages(series);
    // last idx 5, window 5 → mean indices 1..5 = [20,30,40,50,60] = 40
    expect(r.avgNow).toBe(40);
    expect(r.actualNow).toBe(60);
    // idx 4, window 5 → mean [10..50] = 30
    expect(r.avgYesterday).toBe(30);
    // idx 0 → [10]
    expect(r.avgAgo).toBe(10);
    // momentum = actualNow - avgNow = 60 - 40 = 20
    expect(r.momentum).toBe(20);
  });

  it('reports positive momentum when actual exceeds the average', () => {
    const series = [0, 0, 0, 0, 100].map((score) => ({ score }));
    const r = latestConsensusAverages(series);
    // avgNow = mean [0,0,0,0,100] = 20, actualNow = 100 → momentum 80 > 0
    expect(r.momentum).toBeGreaterThan(0);
  });

  it('reports negative momentum when actual is below the average', () => {
    const series = [100, 100, 100, 100, 0].map((score) => ({ score }));
    const r = latestConsensusAverages(series);
    // avgNow = 80, actualNow = 0 → momentum -80 < 0
    expect(r.momentum).toBeLessThan(0);
  });

  it('returns all-null for an empty series', () => {
    expect(latestConsensusAverages([])).toEqual({
      avgNow: null,
      actualNow: null,
      avgYesterday: null,
      avgAgo: null,
      momentum: null,
    });
  });

  it('yields null momentum when avgNow is null', () => {
    const series = [{ score: Number.NaN }];
    const r = latestConsensusAverages(series);
    expect(r.avgNow).toBeNull();
    expect(r.momentum).toBeNull();
  });
});
