/**
 * Thesis route segments pre-rendered at build time when using `output: 'export'`.
 * `/portfolio/theses/{thesisId}` only works on static hosting for ids that have an
 * exported HTML file, so production builds must enumerate the real thesis ids here.
 * `_unlinked` is always included as the fallback segment.
 */
export const THESIS_BUILD_STATIC_PARAMS: { thesisId: string }[] = [{ thesisId: '_unlinked' }];

/**
 * Resolve the thesis ids to pre-render. With Supabase env present (production /
 * Cloudflare Pages builds) the ids come from the `theses` table; without it
 * (CI, local builds) only `_unlinked` is exported. A fetch failure when env IS
 * configured throws: silently falling back would ship 404s for every live
 * thesis link, which is the regression this exists to prevent (#674).
 */
export async function fetchThesisStaticParams(): Promise<{ thesisId: string }[]> {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !key) return THESIS_BUILD_STATIC_PARAMS;

  const res = await fetch(`${url}/rest/v1/theses?select=thesis_id`, {
    headers: { apikey: key, Authorization: `Bearer ${key}` },
  });
  if (!res.ok) {
    throw new Error(`thesis-static-params: theses fetch failed with ${res.status}`);
  }
  const rows: { thesis_id: string | null }[] = await res.json();
  const ids = new Set<string>(THESIS_BUILD_STATIC_PARAMS.map((p) => p.thesisId));
  for (const row of rows) {
    if (row.thesis_id) ids.add(row.thesis_id);
  }
  return [...ids].map((thesisId) => ({ thesisId }));
}
