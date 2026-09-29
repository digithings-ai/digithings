/**
 * Slice 0006 wiring stubs — dummy/test-double data sources for every
 * newly-wired route. Clearly marked: the rewire slice replaces each of
 * these with real Supabase/market-API reads; no production traffic may
 * depend on these values.
 *
 * Fixtures mirror the slice-test doubles (`envelope.test.ts` SNAPSHOT,
 * `brief.test.ts` book(), `performance.test.ts` NAV6/SPY6,
 * `kpis-live.test.ts` POSITIONS, `benchmarks.test.ts` NAV_DATES/SPY,
 * `ledger.test.ts` fakeBook EVENTS/MARKS).
 *
 * Null-book convention (mirrors the slice tests): `asOf === "2020-01-01"`
 * loads no book so the wiring tests can reach the `not_found` path.
 */

import type { CommittedBookSnapshot, EnvelopeSource } from './envelope';
import type { BriefBook, BriefDeps } from './brief';
import type { PerformanceBook, PerformanceDeps } from './performance';
import type { BenchmarksBook, BenchmarksDeps } from './benchmarks';
import type { LedgerBook } from './ledger';
import type { LiveBook, LiveDeps } from './kpis-live';
import type { NavRowInput } from './ssot';

export const STUB_NULL_AS_OF = '2020-01-01';

/** Shared stub NAV history (ascending; builders sort internally anyway). */
export const STUB_NAV_ROWS: NavRowInput[] = [
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
    day_return_pct: -0.9804,
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

export const STUB_SPY6 = [
  { date: '2026-08-20', price: 500 },
  { date: '2026-08-21', price: 505 },
  { date: '2026-08-22', price: 502.5 },
  { date: '2026-08-26', price: 510 },
  { date: '2026-08-27', price: 512 },
  { date: '2026-08-28', price: 515 },
];

/** STUB: committed-book snapshot mirroring `envelope.test.ts` SNAPSHOT. */
export const STUB_SNAPSHOT: CommittedBookSnapshot = {
  snapshotDate: '2026-09-24',
  bookAsOf: '2026-09-24',
  positionDates: ['2026-09-24'],
  positions: [
    {
      ticker: 'DBO',
      weightActual: 5.0031,
      entryPrice: 22.14,
      currentPrice: null,
      unrealizedPnlPct: null,
      sinceEntryReturnPct: null,
      metricsAsOf: null,
    },
    {
      ticker: 'XLV',
      weightActual: 30.1269,
      entryPrice: 100,
      currentPrice: 105,
      unrealizedPnlPct: 5,
      sinceEntryReturnPct: null,
      metricsAsOf: '2026-09-23',
    },
  ],
  navRows: [
    {
      date: '2026-09-24',
      nav: 99.909,
      source: 'legacy_nav_history',
      contract: 'legacy_estimate',
      investedPct: 35.13,
      cashPct: 64.87,
      dayReturnPct: null,
    },
  ],
  metricsInvestedPct: null,
  metricsAsOf: '2026-09-23',
};

/** STUB: `EnvelopeSource` over the in-memory snapshot (no network). */
export function stubEnvelopeSource(): EnvelopeSource {
  return {
    loadBook: async (asOf: string | null) =>
      asOf === STUB_NULL_AS_OF ? null : STUB_SNAPSHOT,
    loadMarketCloses: async () => new Map(),
  };
}

/** STUB: brief book mirroring `brief.test.ts` book(). */
export function stubBriefBook(): BriefBook {
  return {
    navRows: STUB_NAV_ROWS,
    snapshotDate: '2026-08-28',
    positionDates: ['2026-08-28'],
    positionMetricsAsOf: ['2026-08-27'],
    bookWeightInvestedPct: 35.13,
    metricsInvestedPct: 80,
    metricsAsOf: '2026-08-27',
    live: null,
    ledgerEvents: [
      { date: '2026-08-28', ticker: 'XLV', event: 'TRIM', weight_pct: 4.9, prev_weight_pct: 9.9 },
    ],
  };
}

/** STUB: `BriefDeps` (no live lane — persisted path only). */
export function stubBriefDeps(): BriefDeps {
  return {
    loadBriefBook: async (asOf: string | null) =>
      asOf === STUB_NULL_AS_OF ? null : stubBriefBook(),
  };
}

/** STUB: `PerformanceDeps` over the shared NAV + SPY history. */
export function stubPerformanceDeps(): PerformanceDeps {
  return {
    loadPerformanceBook: async (asOf: string | null) =>
      asOf === STUB_NULL_AS_OF
        ? null
        : { navRows: STUB_NAV_ROWS, metricsAsOf: '2026-08-27', benchmarkHistory: STUB_SPY6 },
  };
}

/** STUB: `LiveDeps` snapshot (latest quotes the stub server can see). */
export function stubLiveDeps(): LiveDeps {
  const book: LiveBook = {
    positions: [
      {
        ticker: 'XLV',
        weightPct: 20,
        markPrice: 100,
        effectivePrice: 101,
        isLive: true,
        metricsAsOf: '2026-08-27',
        livePriceDate: '2026-08-28',
      },
      {
        ticker: 'DBO',
        weightPct: 5,
        markPrice: 22.14,
        effectivePrice: 22.14,
        isLive: false,
        metricsAsOf: '2026-08-27',
        livePriceDate: null,
      },
    ],
    navHistory: STUB_NAV_ROWS.map((r) => ({ date: r.date, nav: r.nav })),
    benchmarkHistory: STUB_SPY6,
    benchmarkTicker: 'SPY',
  };
  return { loadLiveBook: async () => book };
}

/** STUB: `BenchmarksDeps` over the shared NAV dates + SPY closes. */
export function stubBenchmarksDeps(): BenchmarksDeps {
  const navDates = STUB_NAV_ROWS.map((r) => r.date);
  const closes = STUB_SPY6.map((p) => ({ date: p.date, close: p.price }));
  return {
    loadBenchmarksBook: async (from: string | null, to: string | null) => {
      if (from === STUB_NULL_AS_OF || to === STUB_NULL_AS_OF) return null;
      return {
        navDates,
        marketCloses: { SPY: closes },
        marketUniverse: ['SPY'],
      };
    },
  };
}

const STUB_LEDGER_EVENTS = [
  {
    date: '2026-09-03',
    ticker: 'XLF',
    event: 'TRIM',
    weight_pct: 4.9,
    prev_weight_pct: 9.9,
    price: 54.1,
    thesis_id: null,
    reason: null,
  },
  {
    date: '2026-06-01',
    ticker: 'GLD',
    event: 'OPEN',
    weight_pct: 10,
    prev_weight_pct: 0,
    price: 180,
    thesis_id: null,
    reason: null,
  },
];

const STUB_LEDGER_MARKS = [
  { date: '2026-08-01', ticker: 'XLF', entry_price: 52.0 },
  { date: '2026-07-15', ticker: 'GLD', entry_price: 190 },
];

/**
 * STUB: in-memory `LedgerBook` mirroring `ledger.test.ts` fakeBook
 * (house-workspace pin enforced, paged reads honored).
 */
export function stubLedgerBook(): LedgerBook {
  return {
    async getJson(path: string): Promise<unknown> {
      const [, query = ''] = path.split('?');
      const params = new URLSearchParams(query);
      if (!params.get('workspace_id')?.includes('6b753576-ced9-5319-9bfa-c5d0aacd9319')) {
        throw new Error('missing house workspace pin');
      }
      const table = path.split('?')[0];
      const source = table === 'position_events' ? STUB_LEDGER_EVENTS : STUB_LEDGER_MARKS;
      let rows = [...source];
      const lte = params.get('date')?.match(/^lte\.(.+)$/)?.[1];
      if (lte) rows = rows.filter((r) => (r as { date: string }).date <= (lte as string));
      const ticker = params.get('ticker')?.match(/^eq\.(.+)$/)?.[1];
      if (ticker) rows = rows.filter((r) => (r as { ticker: string }).ticker === ticker);
      const limit = Number(params.get('limit') ?? '1000');
      const offset = Number(params.get('offset') ?? '0');
      return rows.slice(offset, offset + limit);
    },
  };
}

/** STUB performance/benchmark book builders for MCP use (same doubles). */
export function stubPerformanceBook(): PerformanceBook {
  return {
    navRows: STUB_NAV_ROWS,
    metricsAsOf: '2026-08-27',
    benchmarkHistory: STUB_SPY6,
  };
}

/** STUB benchmarks book builder for MCP use (same doubles). */
export function stubBenchmarksBook(): BenchmarksBook {
  return {
    navDates: STUB_NAV_ROWS.map((r) => r.date),
    marketCloses: { SPY: STUB_SPY6.map((p) => ({ date: p.date, close: p.price })) },
    marketUniverse: ['SPY'],
  };
}
