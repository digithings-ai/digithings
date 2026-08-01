/**
 * Coverage for `fetchThesisStaticParams` — the build-time thesis-route enumerator.
 *
 * Why this file exists (#1759): CI never exercised the configured branch of this
 * function. `deploy-digiquant-cloudflare.yml` runs `scripts/build-digiquant.sh`
 * without `NEXT_PUBLIC_SUPABASE_URL` / `NEXT_PUBLIC_SUPABASE_ANON_KEY`, so the
 * env guard short-circuits on line 32 and the fetch, the pagination loop and the
 * fatal `throw` on line 52 were unreachable in CI. A `theses` fetch failure
 * therefore aborts the Cloudflare Pages production build — freezing the site at
 * its last successful deploy — on a code path no CI job had ever entered.
 *
 * These tests give that path real CI coverage (`test-olympus.yml` runs
 * `npm run test --workspace olympus`) without a live Supabase or a Next build.
 */

import { afterEach, describe, expect, it, vi } from 'vitest';

import { THESIS_BUILD_STATIC_PARAMS, fetchThesisStaticParams } from './thesis-static-params';

const URL_VAR = 'NEXT_PUBLIC_SUPABASE_URL';
const KEY_VAR = 'NEXT_PUBLIC_SUPABASE_ANON_KEY';
const SUPABASE_URL = 'https://stub.supabase.co';

/** Mirrors `THESIS_PARAMS_PAGE` in the module under test (module-private). */
const PAGE_SIZE = 1000;

function jsonResponse(rows: { thesis_id: string | null }[]): Response {
  return new Response(JSON.stringify(rows), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  });
}

function configureEnv(): void {
  vi.stubEnv(URL_VAR, SUPABASE_URL);
  vi.stubEnv(KEY_VAR, 'stub-anon-key');
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe('fetchThesisStaticParams', () => {
  it('exports only the _unlinked fallback when Supabase env is absent', async () => {
    vi.stubEnv(URL_VAR, '');
    vi.stubEnv(KEY_VAR, '');
    const fetchSpy = vi.fn();
    vi.stubGlobal('fetch', fetchSpy);

    await expect(fetchThesisStaticParams()).resolves.toEqual(THESIS_BUILD_STATIC_PARAMS);
    // The CI build-check takes exactly this branch — no network, no throw.
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('throws when the theses fetch fails, rather than shipping 404s', async () => {
    configureEnv();
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response('upstream boom', { status: 503 })),
    );

    // This is the production-only failure the CI build cannot reach: a non-ok
    // response aborts the Pages build instead of silently exporting only
    // `_unlinked` (#674).
    await expect(fetchThesisStaticParams()).rejects.toThrow(
      'thesis-static-params: theses fetch failed with 503',
    );
  });

  it('requests a deterministic order and authenticates with the anon key', async () => {
    configureEnv();
    const fetchSpy = vi.fn().mockResolvedValue(jsonResponse([{ thesis_id: 'alpha' }]));
    vi.stubGlobal('fetch', fetchSpy);

    await fetchThesisStaticParams();

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`${SUPABASE_URL}/rest/v1/theses?select=thesis_id&order=thesis_id`);
    const headers = init.headers as Record<string, string>;
    expect(headers.apikey).toBe('stub-anon-key');
    expect(headers.Range).toBe(`0-${PAGE_SIZE - 1}`);
    expect(headers.Prefer).toBe('count=none');
  });

  it('paginates past the PostgREST page cap and dedupes ids across pages', async () => {
    configureEnv();
    // A full first page forces a second request; `alpha` recurs on both pages
    // the way a thesis with many historical rows does.
    const firstPage = [
      { thesis_id: 'alpha' },
      ...Array.from({ length: PAGE_SIZE - 1 }, (_unused, index) => ({
        thesis_id: `thesis-${index}`,
      })),
    ];
    const secondPage = [{ thesis_id: 'alpha' }, { thesis_id: 'omega' }, { thesis_id: null }];
    const fetchSpy = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(firstPage))
      .mockResolvedValueOnce(jsonResponse(secondPage));
    vi.stubGlobal('fetch', fetchSpy);

    const params = await fetchThesisStaticParams();
    const ids = params.map((param) => param.thesisId);

    expect(fetchSpy).toHaveBeenCalledTimes(2);
    const ranges = fetchSpy.mock.calls.map(
      (call) => (call[1] as RequestInit).headers as Record<string, string>,
    );
    expect(ranges.map((headers) => headers.Range)).toEqual([
      `0-${PAGE_SIZE - 1}`,
      `${PAGE_SIZE}-${2 * PAGE_SIZE - 1}`,
    ]);
    // `_unlinked` + 1000 distinct fetched ids; `alpha` counted once, null dropped.
    expect(new Set(ids).size).toBe(ids.length);
    expect(ids).toHaveLength(PAGE_SIZE + 2);
    expect(ids).toContain('_unlinked');
    expect(ids).toContain('omega');
    expect(ids.filter((id) => id === 'alpha')).toHaveLength(1);
  });
});
