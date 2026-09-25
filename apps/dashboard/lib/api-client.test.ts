/**
 * Slice 0008: tests for the central dashboard API client.
 *
 * Every test stubs `fetch` — no network. Covers the `op.column` encoding
 * contract (must match `apps/dashboard-api/src/tables.ts`), the maybe-single
 * composition, and the error mapping.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  ApiError,
  apiGet,
  apiMaybeSingle,
  apiTable,
  dashboardApiBase,
  encodeTableQuery,
  isApiConfigured,
} from './api-client';

const BASE = 'https://api.test';

function stubEnv(value: string): void {
  process.env.NEXT_PUBLIC_DASHBOARD_API_URL = value;
}

afterEach(() => {
  vi.unstubAllGlobals();
  delete process.env.NEXT_PUBLIC_DASHBOARD_API_URL;
});

describe('dashboardApiBase', () => {
  it('trims trailing slashes and reports configured state', () => {
    stubEnv(`${BASE}//`);
    expect(dashboardApiBase()).toBe(BASE);
    expect(isApiConfigured()).toBe(true);
  });

  it('is unconfigured when the env var is missing', () => {
    expect(dashboardApiBase()).toBe('');
    expect(isApiConfigured()).toBe(false);
  });
});

describe('encodeTableQuery', () => {
  it('encodes the full filter language', () => {
    const qs = encodeTableQuery({
      select: 'date,nav',
      order: [{ column: 'date', ascending: false }, 'id.asc'],
      limit: 50,
      offset: 10,
      eq: { workspace_id: 'w1' },
      ilike: { document_key: 'research-changelog/%' },
      in: { series_id: ['a', 'b'] },
      gte: { date: '2026-09-01' },
      lt: { date: '2026-09-24' },
      retrievalPin: 'pin-1',
    });
    const params = new URLSearchParams(qs);
    expect(params.get('select')).toBe('date,nav');
    expect(params.getAll('order')).toEqual(['date.desc', 'id.asc']);
    expect(params.get('limit')).toBe('50');
    expect(params.get('offset')).toBe('10');
    expect(params.get('eq.workspace_id')).toBe('w1');
    expect(params.get('ilike.document_key')).toBe('research-changelog/%');
    expect(params.get('in.series_id')).toBe('a,b');
    expect(params.get('gte.date')).toBe('2026-09-01');
    expect(params.get('lt.date')).toBe('2026-09-24');
    expect(params.get('retrieval_pin')).toBe('pin-1');
  });

  it('defaults ascending and emits nothing when empty', () => {
    const params = new URLSearchParams(encodeTableQuery({ order: { column: 'date' } }));
    expect(params.getAll('order')).toEqual(['date.asc']);
    expect(encodeTableQuery()).toBe('');
  });
});

describe('apiGet', () => {
  it('throws not_configured without a base URL', async () => {
    await expect(apiGet('/v1/portfolio')).rejects.toMatchObject({ code: 'not_configured' });
  });

  it('returns parsed JSON on 200 and maps error bodies', async () => {
    stubEnv(BASE);
    const fetchMock = vi.fn(async (url: unknown) => {
      if (String(url).includes('/v1/portfolio')) {
        return { ok: true, json: async () => ({ ok: true }) };
      }
      return {
        ok: false,
        status: 404,
        json: async () => ({ error: { code: 'not_found', message: 'nope', details: {} } }),
      };
    });
    vi.stubGlobal('fetch', fetchMock);
    await expect(apiGet('/v1/portfolio')).resolves.toEqual({ ok: true });
    const err = (await apiGet('/v1/nope').catch((e: unknown) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(404);
    expect(err.code).toBe('not_found');
  });
});

describe('apiTable', () => {
  it('keeps repeatable order params and returns rows', async () => {
    stubEnv(BASE);
    const fetchMock = vi.fn(async (_url: unknown) => ({ ok: true, json: async () => [{ date: '2026-09-24' }] }));
    vi.stubGlobal('fetch', fetchMock);
    const rows = await apiTable<{ date: string }>('daily_snapshots', {
      select: 'date',
      order: [{ column: 'date', ascending: false }, { column: 'id', ascending: false }],
      limit: 1,
    });
    expect(rows).toEqual([{ date: '2026-09-24' }]);
    const url = String(fetchMock.mock.calls[0][0]);
    expect(url).toContain('/v1/tables/daily_snapshots?');
    const params = new URLSearchParams(url.split('?')[1]);
    expect(params.getAll('order')).toEqual(['date.desc', 'id.desc']);
  });

  it('rejects a non-array body', async () => {
    stubEnv(BASE);
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => ({ rows: [] }) })));
    await expect(apiTable('positions')).rejects.toMatchObject({ code: 'bad_shape' });
  });
});

describe('apiMaybeSingle', () => {
  it('returns the first row or null', async () => {
    stubEnv(BASE);
    const fetchMock = vi.fn(async (_url: unknown) => ({ ok: true, json: async () => [{ date: '2026-09-24' }] }));
    vi.stubGlobal('fetch', fetchMock);
    await expect(apiMaybeSingle('daily_snapshots')).resolves.toEqual({ date: '2026-09-24' });
    // limit=1 is forced for the single-read composition.
    expect(new URLSearchParams(String(fetchMock.mock.calls[0][0]).split('?')[1]).get('limit')).toBe('1');
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => [] })));
    await expect(apiMaybeSingle('daily_snapshots')).resolves.toBeNull();
  });
});
