/**
 * Self-contained tests for GET /benchmarks (`benchmarks.ts`, contract §6.7).
 * Alignment mirrors the dashboard tearsheet benchmark comparisons; the
 * R2-API-only key fallback carries no Supabase path by construction.
 */
import { describe, expect, it } from 'vitest';

import {
  alignBenchmarkSeries,
  benchmarkOverlapMeetsFloor,
  buildBenchmarksData,
  parseBenchmarksQuery,
  registerBenchmarksRoutes,
  resolveBenchmarkUniverse,
} from './benchmarks';
import { DASHBOARD_BENCHMARK_TICKERS, MIN_OVERLAP_DAYS } from './ssot';

const NAV_DATES = [
  '2026-08-20',
  '2026-08-21',
  '2026-08-22',
  '2026-08-26',
  '2026-08-27',
  '2026-08-28',
];

const SPY = [
  { date: '2026-08-20', close: 500 },
  { date: '2026-08-21', close: 505 },
  { date: '2026-08-22', close: 502.5 },
  { date: '2026-08-26', close: 510 },
  { date: '2026-08-27', close: 512 },
  { date: '2026-08-28', close: 515 },
];

describe('parseBenchmarksQuery', () => {
  it('accepts empty, single and multi-ticker queries', () => {
    expect(parseBenchmarksQuery(new URLSearchParams(''))).toEqual({
      ok: true,
      query: { retrievalPin: null, tickers: null, from: null, to: null },
    });
    expect(parseBenchmarksQuery(new URLSearchParams('tickers=spy, QQQ'))).toEqual({
      ok: true,
      query: { retrievalPin: null, tickers: ['SPY', 'QQQ'], from: null, to: null },
    });
  });
  it('rejects bad tickers, ranges and pins', () => {
    expect(parseBenchmarksQuery(new URLSearchParams('tickers=$$$'))).toMatchObject({
      ok: false,
      code: 'bad_request',
    });
    const reversed = new URLSearchParams('from=2026-08-28&to=2026-08-20');
    expect(parseBenchmarksQuery(reversed)).toMatchObject({
      ok: false,
      code: 'bad_request',
    });
    expect(parseBenchmarksQuery(new URLSearchParams('from=soon'))).toMatchObject({
      ok: false,
      code: 'bad_request',
    });
    expect(parseBenchmarksQuery(new URLSearchParams('asOf=2026-08-28'))).toMatchObject({
      ok: false,
      code: 'bad_request',
    });
  });
});

describe('resolveBenchmarkUniverse', () => {
  it('prefers requested, then market, then the dashboard keys', () => {
    expect(resolveBenchmarkUniverse(['qqq'], ['SPY'])).toEqual(['QQQ']);
    expect(resolveBenchmarkUniverse(null, ['QQQ', 'SPY'])).toEqual(['SPY', 'QQQ']);
    expect(resolveBenchmarkUniverse(null, null)).toEqual([...DASHBOARD_BENCHMARK_TICKERS]);
    expect(resolveBenchmarkUniverse([], [])).toEqual([...DASHBOARD_BENCHMARK_TICKERS]);
  });
});

describe('alignBenchmarkSeries', () => {
  it('as-of forward-fills closes onto NAV dates', () => {
    expect(alignBenchmarkSeries(NAV_DATES, SPY)).toEqual(NAV_DATES.map((date, i) => ({
      date,
      close: SPY[i].close,
    })));
  });
  it('starts the window where history starts, drops bad closes', () => {
    const late = SPY.filter((p) => p.date >= '2026-08-26');
    const aligned = alignBenchmarkSeries(NAV_DATES, late);
    expect(aligned.map((p) => p.date)).toEqual(['2026-08-26', '2026-08-27', '2026-08-28']);
    expect(alignBenchmarkSeries(NAV_DATES, [{ date: '2026-08-20', close: 0 }])).toEqual([]);
    expect(alignBenchmarkSeries(NAV_DATES, [])).toEqual([]);
  });
});

describe('buildBenchmarksData', () => {
  it('aligns every universe ticker to the NAV window', () => {
    const data = buildBenchmarksData(
      { navDates: NAV_DATES, marketCloses: { SPY }, marketUniverse: ['SPY', 'QQQ'] },
      ['SPY'],
      null,
      null,
    );
    expect(data.universe).toEqual(['SPY']);
    expect(data.series.SPY).toHaveLength(6);
    expect(data.series.SPY[0]).toEqual({ date: '2026-08-20', close: 500 });
    expect(data.aligned_start).toBe('2026-08-20');
    expect(data.overlap_days).toBe(6);
  });
  it('falls back to keys with empty series when the market API is empty', () => {
    const data = buildBenchmarksData(
      { navDates: ['2026-08-28'], marketCloses: {}, marketUniverse: null },
      null,
      null,
      null,
    );
    expect(data.universe).toContain('SPY');
    expect(data.series.SPY).toEqual([]);
    expect(data.aligned_start).toBeNull();
    expect(data.overlap_days).toBe(0);
  });
  it('sparse history still renders when overlap clears the floor', () => {
    const navDates = Array.from({ length: 25 }, (_, i) => {
      const t = Date.parse('2026-07-20T00:00:00Z') + i * 86_400_000;
      return new Date(t).toISOString().slice(0, 10);
    });
    const closes = navDates.map((date, i) => ({ date, close: 400 + i }));
    const data = buildBenchmarksData(
      { navDates, marketCloses: { SPY: closes }, marketUniverse: ['SPY'] },
      ['SPY'],
      null,
      null,
    );
    expect(benchmarkOverlapMeetsFloor(data.overlap_days)).toBe(true);
    expect(data.overlap_days).toBeGreaterThanOrEqual(MIN_OVERLAP_DAYS);
    expect(benchmarkOverlapMeetsFloor(6)).toBe(false);
  });
});

describe('registerBenchmarksRoutes', () => {
  it('serves universe + series keyed by NAV tip', async () => {
    const handlers = new Map<string, (req: Request) => Promise<Response>>();
    registerBenchmarksRoutes((path, handler) => handlers.set(path, handler), {
      loadBenchmarksBook: async () => ({
        navDates: NAV_DATES,
        marketCloses: { SPY },
        marketUniverse: ['SPY'],
      }),
    });
    const res = await handlers.get('/benchmarks')!(
      new Request('https://api.test/benchmarks?tickers=SPY'),
    );
    expect(res.status).toBe(200);
    const body = (await res.json()) as {
      data: { universe: string[]; overlap_days: number };
      as_of: string;
    };
    expect(body.data.universe).toEqual(['SPY']);
    expect(body.data.overlap_days).toBe(6);
    expect(body.as_of).toBe('2026-08-28');
  });
});
