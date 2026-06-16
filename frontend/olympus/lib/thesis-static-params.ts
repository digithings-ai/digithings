/**
 * Thesis route segments pre-rendered at build time when using `output: 'export'`.
 * `/portfolio/theses/{thesisId}` only works on static hosting for ids that have an
 * exported HTML file, so production builds must enumerate the real thesis ids here.
 * `_unlinked` is always included as the fallback segment.
 */
export const THESIS_BUILD_STATIC_PARAMS: { thesisId: string }[] = [{ thesisId: '_unlinked' }];

/**
 * PostgREST page size and cap for the thesis id enumeration fetch.
 * The default PostgREST limit of 1000 rows can truncate a large thesis table and
 * cause 404s for tickers not included in the static export.  We paginate using
 * the `Range` header (`offset-end` notation) and dedupe `thesis_id` so each id
 * appears at most once regardless of how many historical rows the table has.
 */
const THESIS_PARAMS_PAGE = 1000;
const THESIS_PARAMS_MAX = 50000; // safety cap — well beyond any realistic thesis count

/**
 * Resolve the thesis ids to pre-render. With Supabase env present (production /
 * Cloudflare Pages builds) the ids come from the `theses` table; without it
 * (CI, local builds) only `_unlinked` is exported. A fetch failure when env IS
 * configured throws: silently falling back would ship 404s for every live
 * thesis link, which is the regression this exists to prevent (#674).
 *
 * Paginates through the full table (PostgREST `Range` header) and dedupes
 * `thesis_id` so a thesis with many historical rows doesn't inflate the export.
 */
export async function fetchThesisStaticParams(): Promise<{ thesisId: string }[]> {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !key) return THESIS_BUILD_STATIC_PARAMS;

  const ids = new Set<string>(THESIS_BUILD_STATIC_PARAMS.map((p) => p.thesisId));
  let offset = 0;

  while (offset < THESIS_PARAMS_MAX) {
    const end = offset + THESIS_PARAMS_PAGE - 1;
    // `order=thesis_id` makes Range-based pagination deterministic — without it
    // PostgREST result order (and thus page boundaries) is undefined.
    const res = await fetch(`${url}/rest/v1/theses?select=thesis_id&order=thesis_id`, {
      headers: {
        apikey: key,
        Authorization: `Bearer ${key}`,
        // PostgREST range-based pagination; `Prefer: count=none` skips the
        // expensive COUNT(*) query that the Range header would otherwise trigger.
        Range: `${offset}-${end}`,
        'Prefer': 'count=none',
      },
    });
    if (!res.ok) {
      throw new Error(`thesis-static-params: theses fetch failed with ${res.status}`);
    }
    const rows: { thesis_id: string | null }[] = await res.json();
    for (const row of rows) {
      if (row.thesis_id) ids.add(row.thesis_id);
    }
    // If we got fewer rows than requested, we've reached the end of the table.
    if (rows.length < THESIS_PARAMS_PAGE) break;
    offset += THESIS_PARAMS_PAGE;
  }

  return [...ids].map((thesisId) => ({ thesisId }));
}
