/**
 * Tests for the slice-0003 mount layer (`mountEnvelopeRoutes`): route
 * registration, CONTRACT.md §1/§2 envelope + error shapes, pin passthrough,
 * and delegation to the pure builders — all against a stub `EnvelopeSource`
 * (no network, no secrets).
 */
import { describe, it, expect, vi, type Mock } from 'vitest';
import { mountEnvelopeRoutes } from './envelope';
import type { MarketCloseFill } from './allocations';
import type {
  AddRoute,
  CommittedBookSnapshot,
  EnvelopeSource,
  RouteHandler,
} from './envelope';

const SNAPSHOT: CommittedBookSnapshot = {
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

function harness(source: EnvelopeSource): Map<string, RouteHandler> {
  const routes = new Map<string, RouteHandler>();
  const addRoute: AddRoute = (_method, path, handler) => {
    routes.set(path, handler);
  };
  mountEnvelopeRoutes(addRoute, source);
  return routes;
}

function stubSource(
  overrides: Omit<Partial<EnvelopeSource>, "loadMarketCloses"> = {},
  snapshot: CommittedBookSnapshot | null = SNAPSHOT,
): EnvelopeSource & {
  loadMarketCloses: Mock<
    (
      tickers: readonly string[],
      retrievalPin: string | null,
    ) => Promise<ReadonlyMap<string, MarketCloseFill>>
  >;
} {
  return {
    loadBook: async () => snapshot,
    loadMarketCloses: vi.fn(async () => new Map()) as Mock<
      (
        tickers: readonly string[],
        retrievalPin: string | null,
      ) => Promise<ReadonlyMap<string, MarketCloseFill>>
    >,
    ...overrides,
  };
}

const get = (path: string) => new Request(`http://worker${path}`);

describe('mountEnvelopeRoutes', () => {
  it('registers the three slice routes', () => {
    const routes = harness(stubSource());
    expect([...routes.keys()].sort()).toEqual(['/allocations', '/nav-series', '/portfolio']);
  });

  it('GET /portfolio returns the §6.1 body inside the §1 envelope', async () => {
    const routes = harness(stubSource());
    const res = await routes.get('/portfolio')!(get('/portfolio?retrieval_pin=rp-1'));
    expect(res.status).toBe(200);
    const body = (await res.json()) as Record<string, unknown>;
    expect(body['retrieval_pin']).toBe('rp-1');
    expect(body['as_of']).toBe('2026-09-24');
    const data = body['data'] as Record<string, unknown>;
    expect(data['book_as_of']).toBe('2026-09-24');
    const invested = data['invested'] as Record<string, unknown>;
    expect(invested['kpi_pct']).toBeCloseTo(35.13, 4);
    expect(invested['envelope_pct']).toBeCloseTo(35.13, 4);
    expect(invested['definition']).toBe('accounting_nav_tip');
    const provenance = body['provenance'] as Record<string, unknown>;
    expect(provenance['contract']).toBe('legacy_estimate');
    expect(provenance['tip_date']).toBe('2026-09-24');
  });

  it('GET /portfolio rejects a malformed asOf with the §2 envelope', async () => {
    const routes = harness(stubSource());
    const res = await routes.get('/portfolio')!(get('/portfolio?asOf=not-a-date'));
    expect(res.status).toBe(400);
    const body = (await res.json()) as {
      error: { code: string; retrieval_pin: string | null };
    };
    expect(body.error.code).toBe('bad_request');
  });

  it('GET /portfolio returns not_found when no book is committed', async () => {
    const routes = harness(stubSource({}, null));
    const res = await routes.get('/portfolio')!(get('/portfolio'));
    expect(res.status).toBe(404);
    const body = (await res.json()) as { error: { code: string } };
    expect(body.error.code).toBe('not_found');
  });

  it('GET /portfolio fails closed when the upstream read throws', async () => {
    const routes = harness(
      stubSource({
        loadBook: async () => {
          throw new Error('boom');
        },
      }),
    );
    const res = await routes.get('/portfolio')!(get('/portfolio'));
    expect(res.status).toBe(502);
    const body = (await res.json()) as { error: { code: string } };
    expect(body.error.code).toBe('upstream_empty');
  });

  it('GET /allocations scales rows and folds valuations', async () => {
    const source = stubSource();
    source.loadMarketCloses.mockResolvedValue(
      new Map([['DBO', { price: 23.0, asOf: '2026-09-24' }]]),
    );
    const routes = harness(source);
    const res = await routes.get('/allocations')!(get('/allocations'));
    expect(res.status).toBe(200);
    const body = (await res.json()) as {
      data: {
        invested_pct: number;
        cash_pct: number;
        invested_definition: string;
        rows: Array<{
          ticker: string;
          scaled_weight_pct: number;
          marks: string;
          unrealized_pct: number | null;
        }>;
        marks_unstamped: boolean;
      };
      provenance: { marks: string };
    };
    expect(body.data.invested_pct).toBeCloseTo(35.13, 4);
    expect(body.data.invested_definition).toBe('accounting_nav_tip');
    expect(body.data.rows.map((r) => r.ticker)).toEqual(['DBO', 'XLV']);
    expect(body.data.rows.find((r) => r.ticker === 'DBO')!.marks).toBe('market_api');
    expect(body.data.rows.find((r) => r.ticker === 'XLV')!.marks).toBe('stored');
    expect(body.data.marks_unstamped).toBe(true);
    expect(body.provenance.marks).toBe('market_api');
    // Market fill requested only for the unstamped row with a basis.
    expect(source.loadMarketCloses).toHaveBeenCalledOnce();
    const tickers = source.loadMarketCloses.mock.calls[0][0] as readonly string[];
    expect([...tickers]).toEqual(['DBO']);
    // Pin forwarded to the upstream read.
    const res2 = await routes.get('/allocations')!(get('/allocations?retrieval_pin=p9'));
    expect(((await res2.json()) as Record<string, unknown>)['retrieval_pin']).toBe('p9');
  });

  it('GET /allocations with include_marks=false skips the market read', async () => {
    const source = stubSource();
    const routes = harness(source);
    const res = await routes.get('/allocations')!(get('/allocations?include_marks=false'));
    expect(res.status).toBe(200);
    expect(source.loadMarketCloses).not.toHaveBeenCalled();
    const body = (await res.json()) as {
      data: { rows: Array<{ ticker: string; marks: string }> };
    };
    expect(body.data.rows.find((r) => r.ticker === 'DBO')!.marks).toBe('unavailable');
  });

  it('GET /nav-series returns seam-chained points with contract labels', async () => {
    const routes = harness(stubSource());
    const res = await routes.get('/nav-series')!(get('/nav-series'));
    expect(res.status).toBe(200);
    const body = (await res.json()) as {
      data: {
        tip: { date: string; contract: string };
        points: Array<{ date: string; contract: string; day_return_pct: number | null }>;
      };
    };
    expect(body.data.tip).toEqual({ date: '2026-09-24', contract: 'legacy_estimate' });
    expect(body.data.points).toHaveLength(1);
    expect(body.data.points[0].day_return_pct).toBeNull();
  });

  it('GET /nav-series honors from/to and rejects malformed dates', async () => {
    const routes = harness(stubSource());
    const empty = (await (
      await routes.get('/nav-series')!(get('/nav-series?from=2026-09-25'))
    ).json()) as { data: { points: unknown[] } };
    expect(empty.data.points).toEqual([]);
    const bad = await routes.get('/nav-series')!(get('/nav-series?from=tomorrow'));
    expect(bad.status).toBe(400);
  });

  it('rejects an over-long retrieval_pin on every route', async () => {
    const routes = harness(stubSource());
    const long = `x`.repeat(129);
    for (const path of ['/portfolio', '/allocations', '/nav-series']) {
      const res = await routes.get(path)!(get(`${path}?retrieval_pin=${long}`));
      expect(res.status).toBe(400);
    }
  });
});
