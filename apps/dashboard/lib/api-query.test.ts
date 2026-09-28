/**
 * Tests for the api-query builder shim (slice 0008 rewire).
 *
 * The shim preserves the PostgREST call-site shape while executing reads
 * through the Workers API. fetch is stubbed; assertions inspect the URL
 * the Worker would receive and the { data, error } result contract.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiQueryBuilder, apiDb, apiHouseBook } from './api-query';

const API = 'https://api.test';

function stubFetch(handler: (url: string) => unknown) {
  (globalThis as Record<string, unknown>).fetch = vi.fn(async (input: unknown) => {
    const url = typeof input === 'string' ? input : String((input as { url: string }).url);
    return {
      ok: true,
      status: 200,
      json: async () => handler(url),
    };
  });
}

beforeEach(() => {
  vi.stubGlobal('__DASHBOARD_API_URL__' as never, undefined);
  process.env.NEXT_PUBLIC_DASHBOARD_API_URL = API;
});

describe('api-query builder', () => {
  it('translates a full chain into one tables request', async () => {
    let seen = '';
    stubFetch((url: string) => {
      seen = url;
      return [{ date: '2026-09-24' }];
    });
    const { data, error } = await apiDb
      .from('documents')
      .select('date,payload')
      .eq('document_key', 'pm-rebalance')
      .order('date', { ascending: false })
      .limit(1);
    expect(error).toBeNull();
    expect(data).toEqual([{ date: '2026-09-24' }]);
    expect(seen).toContain('/v1/tables/documents');
    expect(seen).toContain('select=date%2Cpayload');
    expect(seen).toContain('eq.document_key=pm-rebalance');
    expect(seen).toContain('order=date.desc');
    expect(seen).toContain('limit=1');
  });

  it('maps range() to offset/limit and repeats order keys', async () => {
    let seen = '';
    stubFetch((url: string) => {
      seen = url;
      return [];
    });
    await apiDb.from('position_events').select('*').order('date', { ascending: false }).range(0, 999);
    expect(seen).toContain('offset=0');
    expect(seen).toContain('limit=1000');
    await apiDb.from('theses').select('*').order('date').order('ticker');
    expect(seen.match(/order=/g)?.length).toBe(2);
  });

  it('maybeSingle returns the first row, null on empty, and never throws on API errors', async () => {
    stubFetch(() => [{ id: 1 }, { id: 2 }]);
    const one = await apiDb.from('daily_snapshots').select('id').maybeSingle();
    expect(one.error).toBeNull();
    expect(one.data).toEqual({ id: 1 });

    stubFetch(() => []);
    const none = await apiDb.from('daily_snapshots').select('id').maybeSingle();
    expect(none.error).toBeNull();
    expect(none.data).toBeNull();

    (globalThis as Record<string, unknown>).fetch = vi.fn(async () => ({
      ok: false,
      status: 502,
      json: async () => ({ error: { code: 'upstream_empty' } }),
    }));
    const failed = await apiDb.from('positions').select('*');
    expect(failed.data).toBeNull();
    expect(failed.error).toBeTruthy();
  });

  it('apiHouseBook builds a select on the house table (pin enforced server-side)', async () => {
    let seen = '';
    stubFetch((url: string) => {
      seen = url;
      return [];
    });
    const builder = apiHouseBook('positions', 'ticker');
    expect(builder).toBeInstanceOf(ApiQueryBuilder);
    await builder.order('date', { ascending: false }).limit(5000);
    expect(seen).toContain('/v1/tables/positions');
    expect(seen).toContain('select=ticker');
  });
});
