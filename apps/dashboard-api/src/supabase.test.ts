/**
 * Slice 0008: `supabase.ts` real-source tests. `globalThis.fetch` is stubbed
 * per test with canned PostgREST payloads; the tests pin the request paths
 * (house workspace pin, select/order/limit params), the committed-book
 * assembly, and fail-closed behavior (non-OK upstream → `UpstreamError`).
 */

import { describe, expect, it, vi, afterEach } from 'vitest';
import {
  UpstreamError,
  committedDate,
  createSupabaseSource,
  hasSupabaseEnv,
  loadMarketClosesMap,
  supaGet,
  type SupabaseEnv,
} from './supabase';

const ENV: SupabaseEnv = {
  SUPABASE_URL: 'https://test.supabase.co',
  SUPABASE_SERVICE_ROLE_KEY: 'test-service-key',
};

const FETCHED: string[] = [];

function mockFetch(handler: (url: string) => unknown | Response): void {
  (globalThis as Record<string, unknown>).fetch = vi.fn(async (url: string) => {
    FETCHED.push(url);
    const out = handler(url);
    if (out instanceof Response) return out;
    return Response.json(out);
  });
}

afterEach(() => {
  FETCHED.length = 0;
  vi.unstubAllGlobals();
});

describe('hasSupabaseEnv', () => {
  it('is false without secrets, true with both', () => {
    expect(hasSupabaseEnv({})).toBe(false);
    expect(hasSupabaseEnv({ SUPABASE_URL: 'https://x' })).toBe(false);
    expect(hasSupabaseEnv(ENV)).toBe(true);
  });
});

describe('supaGet', () => {
  it('sends the service-role key and parses JSON', async () => {
    let seen: Record<string, string> = {};
    (globalThis as Record<string, unknown>).fetch = vi.fn(async (_url: string, init: unknown) => {
      seen = (init as { headers: Record<string, string> }).headers;
      return Response.json([{ date: '2026-09-24' }]);
    });
    const rows = (await supaGet(ENV, 'daily_snapshots?select=date')) as { date: string }[];
    expect(rows).toEqual([{ date: '2026-09-24' }]);
    expect(seen.apikey).toBe('test-service-key');
    expect(seen.Authorization).toBe('Bearer test-service-key');
  });

  it('throws UpstreamError on non-OK (fail closed)', async () => {
    (globalThis as Record<string, unknown>).fetch = vi.fn(
      async () => new Response('db down', { status: 500 }),
    );
    await expect(supaGet(ENV, 'positions?select=*')).rejects.toBeInstanceOf(UpstreamError);
    await expect(supaGet(ENV, 'positions?select=*')).rejects.toMatchObject({ status: 500 });
  });
});

describe('committedDate', () => {
  it('picks the latest position date on or before the snapshot', () => {
    expect(committedDate('2026-09-24', ['2026-09-22', '2026-09-24', '2026-09-25'])).toBe(
      '2026-09-24',
    );
    expect(committedDate('2026-09-23', ['2026-09-22', '2026-09-24'])).toBe('2026-09-22');
    expect(committedDate(null, ['2026-09-24'])).toBeNull();
    expect(committedDate('2026-09-24', [])).toBeNull();
  });
});

const NAV_ROWS = [
  {
    date: '2026-09-23',
    nav: 108.4,
    cash_pct: 64.87,
    invested_pct: 35.13,
    day_return_pct: 0.1,
    source: 'finalized_accounting',
    contract: 'finalized_accounting',
    series_seam: false,
  },
  {
    date: '2026-09-24',
    nav: 99.909,
    cash_pct: 64.87,
    invested_pct: 35.13,
    day_return_pct: null,
    source: 'legacy_nav_history',
    contract: 'legacy_estimate',
    series_seam: true,
  },
];

const POSITIONS = [
  {
    date: '2026-09-24',
    ticker: 'XLV',
    weight_pct: 30.1269,
    entry_price: 100,
    current_price: 105,
    unrealized_pnl_pct: 5,
    since_entry_return_pct: null,
    metrics_as_of: '2026-09-23',
  },
  {
    date: '2026-09-24',
    ticker: 'CASH',
    weight_pct: 64.87,
    entry_price: null,
    current_price: null,
    unrealized_pnl_pct: null,
    since_entry_return_pct: null,
    metrics_as_of: null,
  },
];

function mockBook(): void {
  mockFetch((url: string) => {
    if (url.includes('/daily_snapshots')) return [{ date: '2026-09-24' }];
    if (url.includes('/positions?')) return POSITIONS;
    if (url.includes('/public_accounting_nav_history')) return NAV_ROWS;
    if (url.includes('/portfolio_metrics')) {
      return [{ date: '2026-09-23', as_of_date: '2026-09-23', invested_pct: 35.13 }];
    }
    if (url.includes('/position_events')) {
      return [
        { date: '2026-09-24', ticker: 'XLV', event: 'HOLD', weight_pct: 30.1, prev_weight_pct: 30.1 },
      ];
    }
    throw new Error(`unexpected fetch ${url}`);
  });
}

describe('envelope source', () => {
  it('assembles the committed book with the house pin on every read', async () => {
    mockBook();
    const source = createSupabaseSource(ENV);
    const book = await source.envelope.loadBook(null, null);
    expect(book?.snapshotDate).toBe('2026-09-24');
    expect(book?.bookAsOf).toBe('2026-09-24');
    expect(book?.positions).toHaveLength(2);
    expect(book?.positions[0]).toMatchObject({ ticker: 'XLV', weightActual: 30.1269 });
    expect(book?.navRows).toHaveLength(2);
    expect(book?.metricsInvestedPct).toBe(35.13);
    expect(book?.metricsAsOf).toBe('2026-09-23');
    for (const url of FETCHED) {
      if (url.includes('/positions?') || url.includes('/position_events?')) {
        expect(url).toContain('workspace_id=eq.6b753576-ced9-5319-9bfa-c5d0aacd9319');
      }
    }
  });

  it('returns null when no snapshot exists (404 path)', async () => {
    mockFetch((url: string) => {
      if (url.includes('/daily_snapshots')) return [];
      throw new Error(`unexpected fetch ${url}`);
    });
    const source = createSupabaseSource(ENV);
    await expect(source.envelope.loadBook(null, null)).resolves.toBeNull();
  });

  it('propagates UpstreamError (route layer maps to 502)', async () => {
    (globalThis as Record<string, unknown>).fetch = vi.fn(
      async () => new Response('down', { status: 503 }),
    );
    const source = createSupabaseSource(ENV);
    await expect(source.envelope.loadBook(null, null)).rejects.toBeInstanceOf(UpstreamError);
  });
});

describe('brief source', () => {
  it('builds the brief book with day-scoped ledger events', async () => {
    mockBook();
    const source = createSupabaseSource(ENV);
    const book = await source.brief.loadBriefBook(null);
    expect(book?.snapshotDate).toBe('2026-09-24');
    expect(book?.bookWeightInvestedPct).toBeCloseTo(30.1269, 4);
    expect(book?.positionMetricsAsOf).toEqual(['2026-09-23', null]);
    expect(book?.live).toBeNull();
    expect(book?.ledgerEvents).toHaveLength(1);
    const eventUrl = FETCHED.find((u) => u.includes('/position_events?'));
    expect(eventUrl).toContain('date=eq.2026-09-24');
  });
});

describe('market closes', () => {
  it('returns an empty map when the market API is unset', async () => {
    const map = await loadMarketClosesMap(ENV, ['SPY'], '2026-09-01', '2026-09-24');
    expect(map.size).toBe(0);
    expect(FETCHED).toHaveLength(0);
  });

  it('keeps the latest close per ticker across batches', async () => {
    const withMarket: SupabaseEnv = { ...ENV, MARKET_DATA_URL: 'https://m.test' };
    (globalThis as Record<string, unknown>).fetch = vi.fn(async () =>
      Response.json({
        rows: [
          { date: '2026-09-23', ticker: 'SPY', close: 500 },
          { date: '2026-09-24', ticker: 'SPY', close: 505 },
        ],
      }),
    );
    const map = await loadMarketClosesMap(withMarket, ['SPY'], '2026-09-01', '2026-09-24');
    expect(map.get('SPY')).toEqual({ price: 505, asOf: '2026-09-24' });
  });

  it('resolves honest-empty on market failure', async () => {
    const withMarket: SupabaseEnv = { ...ENV, MARKET_DATA_URL: 'https://m.test' };
    (globalThis as Record<string, unknown>).fetch = vi.fn(
      async () => new Response('nope', { status: 500 }),
    );
    const map = await loadMarketClosesMap(withMarket, ['SPY'], '2026-09-01', '2026-09-24');
    expect(map.size).toBe(0);
  });
});

describe('ledger book', () => {
  it('reads PostgREST paths with the service key', async () => {
    mockFetch(() => [{ date: '2026-09-24', ticker: 'XLV', event: 'HOLD' }]);
    const source = createSupabaseSource(ENV);
    const rows = await source.ledger.getJson('position_events?select=date&limit=1');
    expect(rows).toHaveLength(1);
    expect(FETCHED[0]).toContain('/rest/v1/position_events?select=date');
  });
});

describe('fail-closed routing (slice 0008)', () => {
  it('serves 502 upstream_empty — never stub data — when real reads fail', async () => {
    const { default: app } = await import('./index');
    (globalThis as Record<string, unknown>).fetch = vi.fn(
      async () => new Response('down', { status: 503 }),
    );
    const res = await app.fetch(new Request('https://x/portfolio'), ENV);
    expect(res.status).toBe(502);
    const body = (await res.json()) as { error: { code: string } };
    expect(body.error.code).toBe('upstream_empty');
  });

  it('serves stub data when no service key is configured', async () => {
    const { default: app } = await import('./index');
    const res = await app.fetch(new Request('https://x/portfolio'), {});
    expect(res.status).toBe(200);
  });
});
