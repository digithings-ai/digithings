import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '@/lib/api-client';
import {
  KPIS_LIVE_BADGE,
  digiconFailure,
  getAllocations,
  getBenchmarks,
  getBrief,
  getKpisLive,
  getLedger,
  getNavSeries,
  getPerformance,
  getPortfolio,
  getTable,
} from './digicon';

const BASE = 'https://api.test';

function envelope(data: unknown) {
  return {
    data,
    as_of: '2026-09-24',
    retrieval_pin: 'pin-1',
    provenance: {
      source: 'house',
      tip_date: '2026-09-24',
      contract: 'legacy_estimate',
      seam: false,
      marks: 'stored',
    },
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
  delete process.env.NEXT_PUBLIC_DASHBOARD_API_URL;
});

describe('DigiCon getters', () => {
  it('calls the contracted paths and keeps nulls null', async () => {
    process.env.NEXT_PUBLIC_DASHBOARD_API_URL = BASE;
    const fetchMock = vi.fn(async (url: unknown) => {
      const path = String(url);
      if (path.includes('/brief')) {
        return { ok: true, json: async () => envelope({ day_return_pct: null, since_inception_pct: null }) };
      }
      if (path.includes('/portfolio')) {
        return { ok: true, json: async () => envelope({ nav_tip: { nav: null, day_return_pct: null } }) };
      }
      if (path.includes('/allocations')) {
        return {
          ok: true,
          json: async () => envelope({ rows: [{ ticker: 'DBC', current_price: null, unrealized_pct: null }] }),
        };
      }
      if (path.includes('/ledger')) {
        return { ok: true, json: async () => envelope({ events: [], next_cursor: null }) };
      }
      if (path.includes('/performance')) {
        return {
          ok: true,
          json: async () =>
            envelope({ metrics: { alpha_pct: null, information_ratio: null, overlap_days: 4 } }),
        };
      }
      return { ok: false, status: 500, json: async () => ({}) };
    });
    vi.stubGlobal('fetch', fetchMock);

    const brief = await getBrief({ retrievalPin: 'pin-1' });
    const portfolio = await getPortfolio();
    const allocations = await getAllocations();
    const ledger = await getLedger();
    const performance = await getPerformance();

    expect(brief.data.day_return_pct).toBeNull();
    expect(brief.retrieval_pin).toBe('pin-1');
    expect(brief.provenance?.marks).toBe('stored');
    expect(portfolio.data.nav_tip?.nav).toBeNull();
    expect(allocations.data.rows[0].current_price).toBeNull();
    expect(ledger.data.events).toEqual([]);
    expect(performance.data.metrics.alpha_pct).toBeNull();
    expect(performance.data.metrics.information_ratio).toBeNull();

    const urls = fetchMock.mock.calls.map((call) => String(call[0]));
    expect(urls.some((url) => url.startsWith(`${BASE}/brief?`) && url.includes('overlay=auto'))).toBe(true);
    expect(urls.some((url) => url.startsWith(`${BASE}/portfolio`))).toBe(true);
    expect(urls.some((url) => url.includes('/allocations?') && url.includes('include_marks=true'))).toBe(true);
    expect(urls.some((url) => url.startsWith(`${BASE}/ledger`))).toBe(true);
    expect(
      urls.some((url) => url.includes('/performance?') && url.includes('benchmark=SPY') && url.includes('window=inception')),
    ).toBe(true);
  });

  it('surfaces ApiError and does not coerce a failed read into zeros', async () => {
    process.env.NEXT_PUBLIC_DASHBOARD_API_URL = BASE;
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: false,
        status: 502,
        json: async () => ({ error: { code: 'upstream_empty', message: 'upstream empty' } }),
      })),
    );

    const err = await getBrief().catch((error: unknown) => error);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(502);
    expect((err as ApiError).code).toBe('upstream_empty');
    expect(digiconFailure(err)).toEqual({ state: 'error', errorMessage: 'upstream empty' });
    expect(digiconFailure(err).errorMessage).not.toBe('0');
  });

  it('badges live KPIs as live marks', async () => {
    process.env.NEXT_PUBLIC_DASHBOARD_API_URL = BASE;
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: unknown) => {
        expect(String(url)).toContain('/kpis/live');
        return {
          ok: true,
          json: async () =>
            envelope({
              quote_date: '2026-09-24',
              live_vs_mark_pct: null,
              day_return_live_pct: null,
              overlay_eligible: false,
              universe: [],
            }),
        };
      }),
    );
    const live = await getKpisLive();
    expect(live.badge).toBe(KPIS_LIVE_BADGE);
    expect(live.badge).not.toBe('finalized accounting');
    expect(live.data.day_return_live_pct).toBeNull();
  });

  it('calls nav-series and benchmarks without filling a missing close', async () => {
    process.env.NEXT_PUBLIC_DASHBOARD_API_URL = BASE;
    const fetchMock = vi.fn(async (url: unknown) => {
      const path = String(url);
      if (path.includes('/nav-series')) {
        return { ok: true, json: async () => envelope({ points: [{ date: '2026-09-24', nav: null }] }) };
      }
      if (path.includes('/benchmarks')) {
        return {
          ok: true,
          json: async () => envelope({ series: { SPY: [{ date: '2026-09-24', close: null }] }, overlap_days: null }),
        };
      }
      return { ok: false, status: 500, json: async () => ({}) };
    });
    vi.stubGlobal('fetch', fetchMock);
    const nav = await getNavSeries({ from: '2026-09-01', to: '2026-09-24' });
    const benches = await getBenchmarks({ tickers: 'SPY' });
    expect(nav.data.points[0].nav).toBeNull();
    expect(benches.data.series.SPY[0].close).toBeNull();
    expect(benches.data.overlap_days).toBeNull();
    const urls = fetchMock.mock.calls.map((call) => String(call[0]));
    expect(urls.some((url) => url.includes('/nav-series?') && url.includes('from=2026-09-01'))).toBe(true);
    expect(urls.some((url) => url.includes('/benchmarks?') && url.includes('tickers=SPY'))).toBe(true);
  });

  it('reads an allowlisted table and rejects names that are not on the contract', async () => {
    process.env.NEXT_PUBLIC_DASHBOARD_API_URL = BASE;
    const fetchMock = vi.fn(async (url: unknown) => {
      expect(String(url)).toContain('/v1/tables/theses');
      return { ok: true, json: async () => [{ thesis_id: 'T-1' }] };
    });
    vi.stubGlobal('fetch', fetchMock);
    const rows = await getTable<{ thesis_id: string }>('theses', { eq: { date: '2026-09-24' } });
    expect(rows.data).toEqual([{ thesis_id: 'T-1' }]);
    expect(rows.provenance).toBeNull();

    const missing = await getTable('not_a_table').catch((error: unknown) => error);
    expect(missing).toBeInstanceOf(ApiError);
    expect((missing as ApiError).code).toBe('not_found');
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
