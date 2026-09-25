/**
 * Slice 0008: `tables.ts` allowlisted-read tests. `buildTableQuery` is
 * asserted pure (PostgREST mapping, house pin, rejections); the route is
 * driven through `app.fetch` with a stubbed `globalThis.fetch`.
 */

import { describe, expect, it, vi, afterEach } from 'vitest';
import app, { type Env } from './index';
import { buildTableQuery, HOUSE_WORKSPACE_ID, TablesQueryError } from './tables';

const ENV: Env = {
  SUPABASE_URL: 'https://test.supabase.co',
  SUPABASE_SERVICE_ROLE_KEY: 'test-service-key',
};

const FETCHED: string[] = [];

function mockFetch(rows: unknown): void {
  (globalThis as Record<string, unknown>).fetch = vi.fn(async (url: string) => {
    FETCHED.push(url);
    return Response.json(rows);
  });
}

afterEach(() => {
  FETCHED.length = 0;
  vi.unstubAllGlobals();
});

function qs(params: Record<string, string>): URLSearchParams {
  return new URLSearchParams(params);
}

describe('buildTableQuery', () => {
  it('maps select/eq/order/limit to PostgREST params', () => {
    const q = buildTableQuery(
      'daily_snapshots',
      qs({ select: 'date,snapshot', 'eq.run_type': 'daily', order: 'date.desc', limit: '1' }),
    );
    expect(q).toContain('daily_snapshots?');
    expect(q).toContain(`select=${encodeURIComponent('date,snapshot')}`);
    expect(q).toContain('run_type=eq.daily');
    expect(q).toContain('order=date.desc');
    expect(q).toContain('limit=1');
  });

  it('maps ilike/like/in/lt/lte/gt/gte filters', () => {
    const q = buildTableQuery(
      'documents',
      qs({
        select: 'date,payload',
        'ilike.document_key': 'research-changelog/%',
        'in.series_id': 'a,b',
        'gte.obs_date': '2026-01-01',
      }),
    );
    expect(q).toContain('document_key=ilike.research-changelog%2F%25');
    expect(q).toContain('series_id=in.%28a%2Cb%29');
    expect(q).toContain('obs_date=gte.2026-01-01');
  });

  it('forces the house workspace pin on house tables', () => {
    const q = buildTableQuery('positions', qs({ select: '*' }));
    expect(q).toContain(`workspace_id=eq.${HOUSE_WORKSPACE_ID}`);
    const free = buildTableQuery('daily_snapshots', qs({ select: '*' }));
    expect(free).not.toContain('workspace_id');
  });

  it('never forwards retrieval_pin upstream', () => {
    const q = buildTableQuery('positions', qs({ select: '*', retrieval_pin: 'pin-9' }));
    expect(q).not.toContain('retrieval_pin');
  });

  it('rejects tables outside the allowlist', () => {
    try {
      buildTableQuery('portfolio_ledger_commits', qs({ select: '*' }));
      throw new Error('no throw');
    } catch (err) {
      expect(err).toBeInstanceOf(TablesQueryError);
      expect((err as TablesQueryError).code).toBe('not_found');
    }
  });

  it('rejects unknown operators and bad limits', () => {
    expect(() => buildTableQuery('positions', qs({ 'fuzzy.ticker': 'X' }))).toThrowError(
      TablesQueryError,
    );
    expect(() => buildTableQuery('positions', qs({ limit: '0' }))).toThrowError(TablesQueryError);
    expect(() => buildTableQuery('positions', qs({ limit: '5001' }))).toThrowError(TablesQueryError);
    expect(() => buildTableQuery('positions', qs({ order: 'date.sideways' }))).toThrowError(
      TablesQueryError,
    );
  });
});

describe('GET /v1/tables/:table', () => {
  it('serves rows and forwards the PostgREST query upstream', async () => {
    mockFetch([{ date: '2026-09-24' }]);
    const res = await app.fetch(
      new Request('https://api.test/v1/tables/daily_snapshots?select=date&order=date.desc&limit=1'),
      ENV,
    );
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual([{ date: '2026-09-24' }]);
    expect(FETCHED).toHaveLength(1);
    expect(FETCHED[0]).toContain('/rest/v1/daily_snapshots?');
    expect(FETCHED[0]).toContain('order=date.desc');
  });

  it('returns 404 for a non-allowlisted table', async () => {
    mockFetch([]);
    const res = await app.fetch(
      new Request('https://api.test/v1/tables/portfolio_ledger_commits?select=*'),
      ENV,
    );
    expect(res.status).toBe(404);
    expect(FETCHED).toHaveLength(0);
  });

  it('returns 502 without worker env (fail-closed, no stub lane)', async () => {
    mockFetch([]);
    const res = await app.fetch(
      new Request('https://api.test/v1/tables/positions?select=*'),
      {},
    );
    expect(res.status).toBe(502);
    expect(FETCHED).toHaveLength(0);
  });
});
