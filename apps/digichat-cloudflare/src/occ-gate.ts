/**
 * Edge gate for the OCC page on Pages (DIG-1210). `/chat/occ` is served by
 * Pages; this Worker route sits in front of it. Without the valid invite key
 * (`?token=`, compared to the OCC_INVITE_KEY secret) the visitor gets the
 * site's standard 404 page, with no hint that the path exists.
 */
export function isOccPagePath(pathname: string): boolean {
  return pathname === "/chat/occ" || pathname.startsWith("/chat/occ/");
}

function timingSafeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

export function occInviteValid(url: URL, expected: string | undefined): boolean {
  const want = expected?.trim();
  const got = url.searchParams.get("token")?.trim();
  if (!want || !got) return false;
  return timingSafeEqual(got, want);
}

/** Standard site 404: Pages' own not-found page for a path that does not exist. */
export async function siteNotFound(url: URL, fetcher: typeof fetch = fetch): Promise<Response> {
  const probe = new URL("/__no_such_page__/", url.origin);
  const res = await fetcher(probe.toString(), { headers: { accept: "text/html" } });
  return new Response(res.body, {
    status: 404,
    headers: {
      "content-type": res.headers.get("content-type") ?? "text/html; charset=utf-8",
      "cache-control": "no-store",
    },
  });
}
