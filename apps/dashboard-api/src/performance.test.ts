/**
 * Self-contained tests for GET /performance (`performance.ts`, contract §6.4).
 * Fixture expectations verified against the client Tearsheet/ssot derivations
 * via scratch parity (overlay-off Brief matches Tearsheet within 0.05pp).
 */
import { describe, expect, it } from 'vitest';

import {
  buildPerformanceProvenance,
  getPerformanceBundle,
  parsePerformanceQuery,
  registerPerformanceRoutes,
  type PerformanceBook,
} from './performance';
import { buildPerformanceSsotMeta, persistedHeadlinesAgree } from './ssot';

const NAV6 = [
  { date: '2026-08-20', nav: 100, source: 'legacy_nav_history', contract: 'legacy_estimate' },
  {
    date: '2026-08-21',
    nav: 102,
    day_return_pct: 2,
    source: 'legacy_nav_history',
    contract: 'legacy_estimate',
  },
  {
    date: '2026-08-22',
    nav: 101,
    day_return_pct: null,
    source: 'legacy_nav_history',
    contract: 'legacy_estimate',
  },
  {
    date: '2026-08-26',
    nav: 200,
    day_return_pct: null,
    source: 'finalized_accounting',
    contract: 'finalized_accounting',
    series_seam: true,
  },
  {
    date: '2026-08-27',
    nav: 202,
    day_return_pct: null,
    source: 'finalized_accounting',
    contract: 'finalized_accounting',
  },
  {
    date: '2026-08-28',
    nav: 204.04,
    day_return_pct: null,
    source: 'finalized_accounting',
    contract: 'finalized_accounting',
  },
];

const SPY6 = [
  { date: '2026-08-20', price: 500 },
  { date: '2026-08-21', price: 505 },
  { date: '2026-08-22', price: 502.5 },
  { date: '2026-08-26', price: 510 },
  { date: '2026-08-27', price: 512 },
  { date: '2026-08-28', price: 515 },
];

type ThirtyDay = {
  nav: PerformanceBook['navRows'];
  bench: { date: string; price: number }[];
};
function thirtyDay(): ThirtyDay {
  const nav: PerformanceBook['navRows'] = [];
  const bench: { date: string; price: number }[] = [];
  let n = 100;
  let b = 400;
  const d0 = Date.parse('2026-07-20T00:00:00Z');
  for (let i = 0; i < 30; i += 1) {
    const date = new Date(d0 + i * 86_400_000).toISOString().slice(0, 10);
    if (i > 0) {
      const rp = i % 2 === 1 ? 0.01 : -0.005;
      n *= 1 + rp;
      b *= 1 + rp / 2;
    }
    nav.push({ date, nav: n, source: 'finalized_accounting', contract: 'finalized_accounting' });
    bench.push({ date, price: b });
  }
  return { nav, bench };
}

describe('parsePerformanceQuery', () => {
  it('defaults benchmark SPY + inception window', () => {
    expect(parsePerformanceQuery(new URLSearchParams(''))).toEqual({
      ok: true,
      query: { asOf: null, retrievalPin: null, benchmark: 'SPY', window: 'inception' },
    });
  });
  it('rejects malformed params', () => {
    expect(parsePerformanceQuery(new URLSearchParams('window=5y'))).toMatchObject({
      ok: false,
      code: 'bad_request',
    });
    expect(parsePerformanceQuery(new URLSearchParams('benchmark=$$$'))).toMatchObject({
      ok: false,
      code: 'bad_request',
    });
    expect(parsePerformanceQuery(new URLSearchParams('asOf=soon'))).toMatchObject({
      ok: false,
      code: 'bad_request',
    });
  });
});

describe('getPerformanceBundle', () => {
  it('charts the chained series with forward-filled weekends', () => {
    const data = getPerformanceBundle(
      { navRows: NAV6, metricsAsOf: '2026-08-27', benchmarkHistory: SPY6 },
      'SPY',
      'inception',
    );
    expect(data.nav.tip_date).toBe('2026-08-28');
    expect(data.nav.base100_tip).toBe(103.0402);
    expect(data.nav.points.map((p) => p.date)).toEqual([
      '2026-08-20',
      '2026-08-21',
      '2026-08-22',
      '2026-08-23',
      '2026-08-24',
      '2026-08-25',
      '2026-08-26',
      '2026-08-27',
      '2026-08-28',
    ]);
    expect(data.nav.points[0].day_return_pct).toBeNull();
    expect(data.nav.points[3]).toEqual({ date: '2026-08-23', index: 101, day_return_pct: 0 });
    // Headline agrees with the chart it plots.
    expect(data.metrics.since_inception_pct).toBe(3.0402);
    expect(
      persistedHeadlinesAgree(data.metrics.since_inception_pct, data.nav.base100_tip! - 100),
    ).toBe(true);
  });
  it('guards the tip day return and reports signed lag', () => {
    const data = getPerformanceBundle(
      { navRows: NAV6, metricsAsOf: '2026-08-27', benchmarkHistory: SPY6 },
      'SPY',
      'inception',
    );
    expect(data.metrics.day_return_pct).toBeCloseTo(1.0099, 4);
    expect(data.stale).toEqual({
      lag_days: 1,
      lag_direction: 'metrics lag',
      metrics_as_of: '2026-08-27',
    });
  });
  it('reports nav lag when the metrics stamp runs ahead of the tip', () => {
    const data = getPerformanceBundle(
      { navRows: NAV6, metricsAsOf: '2026-08-29', benchmarkHistory: SPY6 },
      'SPY',
      'inception',
    );
    expect(data.stale.lag_days).toBe(-1);
    expect(data.stale.lag_direction).toBe('nav lag');
  });
  it('computes excess over the NAV-aligned window, nulls alpha/IR below the floor', () => {
    const data = getPerformanceBundle(
      { navRows: NAV6, metricsAsOf: '2026-08-27', benchmarkHistory: SPY6 },
      'SPY',
      'inception',
    );
    // Current run 08-26→08-28: Rp = 2.02, Rb = 515/510−1 = 0.9804.
    expect(data.metrics.excess_return_pct).toBeCloseTo(1.0396, 4);
    expect(data.metrics.overlap_days).toBe(2);
    expect(data.metrics.alpha_pct).toBeNull();
    expect(data.metrics.information_ratio).toBeNull();
    expect(data.metrics.beta).toBeNull();
    expect(data.benchmark).toEqual({ ticker: 'SPY', aligned_start: '2026-08-26' });
  });
  it('clears the 20-pair floor on a real sample', () => {
    const { nav, bench } = thirtyDay();
    const data = getPerformanceBundle(
      { navRows: nav, metricsAsOf: nav.at(-1)!.date, benchmarkHistory: bench },
      'SPY',
      'inception',
    );
    expect(data.metrics.overlap_days).toBeGreaterThanOrEqual(20);
    expect(data.metrics.beta).not.toBeNull();
    expect(data.metrics.alpha_pct).not.toBeNull();
    expect(data.metrics.information_ratio).not.toBeNull();
    expect(data.metrics.excess_return_pct).not.toBeNull();
  });
  it('scopes the chart to the requested window', () => {
    const { nav, bench } = thirtyDay();
    const full = getPerformanceBundle(
      { navRows: nav, metricsAsOf: nav.at(-1)!.date, benchmarkHistory: bench },
      'SPY',
      'inception',
    );
    const m3 = getPerformanceBundle(
      { navRows: nav, metricsAsOf: nav.at(-1)!.date, benchmarkHistory: bench },
      'SPY',
      '3m',
    );
    expect(m3.nav.points.length).toBeLessThanOrEqual(full.nav.points.length);
    expect(m3.nav.tip_date).toBe(full.nav.tip_date);
  });
});

describe('getPerformanceBundle ssot', () => {
  const legs = {
    snapshotDate: '2026-08-28',
    positionDates: ['2026-08-28'],
    positionMetricsAsOf: ['2026-08-27'],
    bookWeightInvestedPct: 35.13,
    metricsInvestedPct: 80,
  };
  it('serves the full SSOT chrome from the book legs', () => {
    const data = getPerformanceBundle(
      { navRows: NAV6, metricsAsOf: '2026-08-27', benchmarkHistory: SPY6, ...legs },
      'SPY',
      'inception',
    );
    expect(data.ssot).toEqual(
      buildPerformanceSsotMeta({ navRows: NAV6, metricsAsOf: '2026-08-27', ...legs }),
    );
    expect(data.ssot.navAsOf).toBe('2026-08-28');
    expect(data.ssot.bookAsOf).toBe('2026-08-28');
    expect(data.ssot.marksUnstamped).toBe(false);
    expect(data.ssot.investedDefinition).toBe('book_weights');
  });
  it('degrades honestly when the ssot legs are absent', () => {
    const data = getPerformanceBundle(
      { navRows: NAV6, metricsAsOf: '2026-08-27', benchmarkHistory: SPY6 },
      'SPY',
      'inception',
    );
    expect(data.ssot.bookAsOf).toBeNull();
    expect(data.ssot.marksUnstamped).toBe(true);
  });
});
describe('buildPerformanceProvenance', () => {
  it('badges the tip without implying finalized history', () => {
    expect(
      buildPerformanceProvenance({ navRows: NAV6, metricsAsOf: null, benchmarkHistory: [] }),
    ).toEqual({
      source: 'public_accounting_nav_history',
      tip_date: '2026-08-28',
      contract: 'finalized_accounting',
      seam: false,
      marks: 'stored',
    });
  });
});

describe('registerPerformanceRoutes', () => {
  it('serves the bundle keyed by tip date', async () => {
    const handlers = new Map<string, (req: Request) => Promise<Response>>();
    registerPerformanceRoutes((path, handler) => handlers.set(path, handler), {
      loadPerformanceBook: async () => ({
        navRows: NAV6,
        metricsAsOf: '2026-08-27',
        benchmarkHistory: SPY6,
      }),
    });
    const res = await handlers.get('/performance')!(
      new Request('https://api.test/performance?benchmark=SPY&window=inception'),
    );
    expect(res.status).toBe(200);
    const body = (await res.json()) as {
      data: { nav: { tip_date: string }; metrics: { overlap_days: number } };
      as_of: string;
    };
    expect(body.data.nav.tip_date).toBe('2026-08-28');
    expect(body.as_of).toBe('2026-08-28');
    const bad = await handlers.get('/performance')!(
      new Request('https://api.test/performance?window=5y'),
    );
    expect(bad.status).toBe(400);
  });
});
