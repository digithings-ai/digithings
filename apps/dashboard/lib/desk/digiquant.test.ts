import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '@/lib/api-client';
import { getAllocations, getBrief, getPortfolio } from './digiquant';

const BASE = 'https://api.test';

afterEach(() => {
  vi.unstubAllGlobals();
  delete process.env.NEXT_PUBLIC_DASHBOARD_API_URL;
});

function stubFetch(body: unknown, status = 200): void {
  process.env.NEXT_PUBLIC_DASHBOARD_API_URL = BASE;
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => ({
      ok: status >= 200 && status < 300,
      status,
      json: async () => body,
    })),
  );
}

describe('digiquant house reads', () => {
  it('calls GET /brief with overlay and returns the envelope without filling zeros', async () => {
    stubFetch({
      data: {
        book_as_of: '2026-09-30',
        nav_tip: { date: '2026-09-30', nav: null, contract: 'legacy_estimate' },
        day_return_pct: null,
        since_inception_pct: null,
        since_inception_start_date: null,
        overlay: { active: false, live_vs_mark_pct: 0, badge: 'legacy estimate' },
        invested_pct: null,
        session_events: [],
      },
      as_of: '2026-09-30',
      retrieval_pin: 'pin-1',
      provenance: { source: 'book', tip_date: '2026-09-30', contract: null, seam: false, marks: 'unavailable' },
    });

    const result = await getBrief({ overlay: 'auto' });
    const url = String(vi.mocked(fetch).mock.calls[0]?.[0]);
    expect(url).toBe(`${BASE}/brief?overlay=auto`);
    expect(result.data.day_return_pct).toBeNull();
    expect(result.data.since_inception_pct).toBeNull();
    expect(result.retrievalPin).toBe('pin-1');
    expect(result.provenance?.source).toBe('book');
  });

  it('surfaces ApiError from GET /portfolio instead of a zero book', async () => {
    stubFetch({ error: { code: 'not_found', message: 'no committed book' } }, 404);
    await expect(getPortfolio()).rejects.toBeInstanceOf(ApiError);
    await expect(getPortfolio()).rejects.toMatchObject({ status: 404, code: 'not_found' });
  });

  it('asks GET /allocations for marks', async () => {
    stubFetch({
      data: {
        book_as_of: null,
        invested_pct: null,
        cash_pct: null,
        invested_definition: 'unavailable',
        rows: [],
        marks_unstamped: true,
      },
      as_of: null,
      retrieval_pin: null,
      provenance: null,
    });
    await getAllocations({ includeMarks: true });
    const url = String(vi.mocked(fetch).mock.calls[0]?.[0]);
    expect(url).toContain('/allocations?');
    expect(url).toContain('include_marks=true');
  });
});
