/**
 * #4013 — dashboard reads prices from the R2-backed market API.
 *
 * `fetchMarketCloses` / `fetchMarketTickers` are the only browser callers of
 * `/v1/market/*`; the three read sites (comparable history, position price fill,
 * holding marks) hand off to them unconditionally (#4053, R2-only — no Supabase
 * fallbacks). Every test stubs `fetch` — no network.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { existsSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { fetchMarketCloses, fetchMarketTickers } from './market-data';
import { fetchComparablePriceHistory, resolveTickerUniverse } from './queries';
import { DASHBOARD_BENCHMARK_TICKERS, sortTickerUniverse } from './benchmark-tickers';
import type { BenchmarkHistoryMap } from './types';

const here = dirname(fileURLToPath(import.meta.url));
const MARKET_URL = 'https://graph.digithings.ai';

function jsonResponse(body: unknown, ok = true, status = 200) {
  return { ok, status, json: async () => body };
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

describe('fetchMarketCloses', () => {
  it('maps worker rows and passes the window', async () => {
    vi.stubEnv('NEXT_PUBLIC_MARKET_DATA_URL', MARKET_URL);
    const fetchMock = vi.fn(async (url: string) => ({
      ok: true,
      json: async () => ({ as_of: '2026-09-11', rows: [{ date: '2026-09-10', ticker: 'GLD', close: 250 }] }),
    }));
    vi.stubGlobal('fetch', fetchMock);
    const rows = await fetchMarketCloses(['GLD'], '2026-09-01', '2026-09-11');
    expect(rows).toEqual([{ date: '2026-09-10', ticker: 'GLD', close: 250 }]);
    expect(String(fetchMock.mock.calls[0][0])).toContain(
      '/v1/market/closes?tickers=GLD&from=2026-09-01&to=2026-09-11'
    );
  });

  it('returns [] when unconfigured', async () => {
    vi.stubEnv('NEXT_PUBLIC_MARKET_DATA_URL', '');
    expect(await fetchMarketCloses(['GLD'], '2026-09-01', '2026-09-11')).toEqual([]);
  });

  it('batches requests at the 25-ticker worker cap', async () => {
    vi.stubEnv('NEXT_PUBLIC_MARKET_DATA_URL', MARKET_URL);
    const tickers = Array.from({ length: 26 }, (_, i) => `T${i + 1}`);
    const fetchMock = vi.fn(async (url: string) => {
      const asked = new URL(url).searchParams.get('tickers')?.split(',') ?? [];
      return jsonResponse({
        rows: asked.map((ticker) => ({ date: '2026-09-10', ticker, close: 1 })),
      });
    });
    vi.stubGlobal('fetch', fetchMock);
    const rows = await fetchMarketCloses(tickers, '2026-09-01', '2026-09-11');
    expect(fetchMock).toHaveBeenCalledTimes(2);
    const batches = fetchMock.mock.calls.map(
      ([url]) => new URL(String(url)).searchParams.get('tickers')?.split(',') ?? []
    );
    expect(batches.map((batch) => batch.length)).toEqual([25, 1]);
    expect(batches.flat()).toEqual(tickers);
    expect(rows).toHaveLength(26);
  });

  it('returns [] when the worker rejects a batch', async () => {
    vi.stubEnv('NEXT_PUBLIC_MARKET_DATA_URL', MARKET_URL);
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ error: 'bad' }, false, 400)));
    expect(await fetchMarketCloses(['GLD'], '2026-09-01', '2026-09-11')).toEqual([]);
    expect(errorSpy).toHaveBeenCalledWith('fetchMarketCloses:', 400);
  });

  it('normalizes a trailing slash on the base URL', async () => {
    vi.stubEnv('NEXT_PUBLIC_MARKET_DATA_URL', `${MARKET_URL}/`);
    const fetchMock = vi.fn(async (_url: string) => jsonResponse({ rows: [] }));
    vi.stubGlobal('fetch', fetchMock);
    await fetchMarketCloses(['GLD'], '2026-09-01', '2026-09-11');
    expect(String(fetchMock.mock.calls[0][0])).toBe(
      `${MARKET_URL}/v1/market/closes?tickers=GLD&from=2026-09-01&to=2026-09-11`
    );
  });
});

describe('fetchMarketTickers', () => {
  it('returns the worker ticker list', async () => {
    vi.stubEnv('NEXT_PUBLIC_MARKET_DATA_URL', MARKET_URL);
    const fetchMock = vi.fn(async (_url: string) =>
      jsonResponse({ as_of: '2026-09-11', tickers: ['GLD', 'SPY'] })
    );
    vi.stubGlobal('fetch', fetchMock);
    expect(await fetchMarketTickers()).toEqual(['GLD', 'SPY']);
    expect(String(fetchMock.mock.calls[0][0])).toBe(`${MARKET_URL}/v1/market/tickers`);
  });

  it('returns [] when unconfigured', async () => {
    vi.stubEnv('NEXT_PUBLIC_MARKET_DATA_URL', '');
    expect(await fetchMarketTickers()).toEqual([]);
  });

  it('returns [] when the worker rejects the tickers call', async () => {
    vi.stubEnv('NEXT_PUBLIC_MARKET_DATA_URL', MARKET_URL);
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ error: 'bad' }, false, 500)));
    expect(await fetchMarketTickers()).toEqual([]);
    expect(errorSpy).toHaveBeenCalledWith('fetchMarketTickers:', 500);
  });

  it('returns [] when the tickers fetch throws', async () => {
    vi.stubEnv('NEXT_PUBLIC_MARKET_DATA_URL', MARKET_URL);
    vi.spyOn(console, 'error').mockImplementation(() => {});
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new Error('network disabled in tests');
      })
    );
    expect(await fetchMarketTickers()).toEqual([]);
  });
});

describe('fetchComparablePriceHistory market path', () => {
  it('maps market rows into BenchmarkHistoryMap (chronological, current = last close)', async () => {
    vi.stubEnv('NEXT_PUBLIC_MARKET_DATA_URL', MARKET_URL);
    const fetchMock = vi.fn(async (_url: string) =>
      jsonResponse({
        as_of: '2026-09-11',
        // Deliberately not chronological: the worker sorts, but batching must not
        // be relied on for order — history feeds charts.
        rows: [
          { date: '2026-09-11', ticker: 'GLD', close: 260 },
          { date: '2026-09-10', ticker: 'GLD', close: 250 },
        ],
      })
    );
    vi.stubGlobal('fetch', fetchMock);
    const out = await fetchComparablePriceHistory(['gld'], '2026-09-01', '2026-09-11');
    expect(out).toEqual({
      GLD: {
        current: 260,
        history: [
          { date: '2026-09-10', price: 250 },
          { date: '2026-09-11', price: 260 },
        ],
      },
    });
    expect(String(fetchMock.mock.calls[0][0])).toContain('tickers=GLD&from=2026-09-01&to=2026-09-11');
  });

  it('returns {} when the market API is unconfigured', async () => {
    vi.stubEnv('NEXT_PUBLIC_MARKET_DATA_URL', '');
    const networkBlocked = vi.fn(async () => {
      throw new Error('network disabled in tests');
    });
    vi.stubGlobal('fetch', networkBlocked);
    expect(await fetchComparablePriceHistory(['GLD'], '2026-09-01', '2026-09-11')).toEqual({});
  });
});

describe('dashboard market-data wiring', () => {
  const read = (file: string) => {
    const path = join(here, file);
    if (!existsSync(path)) throw new Error(`missing ${path}`);
    return readFileSync(path, 'utf8');
  };

  it('position price fill reads the market API when configured', () => {
    const src = read('queries.ts');
    expect(src).toContain("from './market-data'");
    expect(src).toContain('fetchMarketCloses(posTickers');
  });

  it('holding marks read the market API when configured', () => {
    const src = read('observability-queries.ts');
    expect(src).toContain("from './market-data'");
    expect(src).toContain('fetchMarketCloses(openTickers');
  });

  it('universe comes from the market tickers API, not the price_history_tickers view', () => {
    const src = read('queries.ts');
    expect(src).toContain('fetchMarketTickers(');
    expect(src).not.toContain("from('price_history_tickers')");
  });

  it('market reads have no isMarketDataConfigured gate', () => {
    for (const file of ['market-data.ts', 'queries.ts', 'observability-queries.ts']) {
      expect(read(file)).not.toContain('isMarketDataConfigured');
    }
  });

  it('dead price_history readers are gone (no fetchPositionPriceChart, no trading_calendar)', () => {
    const src = read('queries.ts');
    expect(src).not.toContain('fetchPositionPriceChart');
    expect(src).not.toContain("from('price_history')");
    expect(src).not.toContain('trading_calendar');
  });
});

describe('ticker universe fallback', () => {
  const benchmarks = {
    GLD: { current: 260, history: [{ date: '2026-09-11', price: 260 }] },
  } as BenchmarkHistoryMap;

  it('empty tickers API falls back to benchmark keys + DASHBOARD_BENCHMARK_TICKERS', async () => {
    vi.stubEnv('NEXT_PUBLIC_MARKET_DATA_URL', MARKET_URL);
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ as_of: '2026-09-11', tickers: [] })));
    const universeTickers = await fetchMarketTickers();
    expect(universeTickers).toEqual([]);
    expect(resolveTickerUniverse(universeTickers, benchmarks)).toEqual(
      sortTickerUniverse([...Object.keys(benchmarks), ...DASHBOARD_BENCHMARK_TICKERS])
    );
  });

  it('non-empty tickers API returns the sorted R2 universe', async () => {
    vi.stubEnv('NEXT_PUBLIC_MARKET_DATA_URL', MARKET_URL);
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ as_of: '2026-09-11', tickers: ['SPY', 'GLD'] })));
    expect(resolveTickerUniverse(await fetchMarketTickers(), benchmarks)).toEqual(
      sortTickerUniverse(['SPY', 'GLD'])
    );
  });
});
