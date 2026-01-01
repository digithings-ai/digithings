/**
 * Embed token transport (DIG-3523).
 *
 * The per-tenant embed secret used to travel as `?token=` all the way into
 * the server render, and Next.js serialised the request URL into the App
 * Router flight payload (`"c":["","embed?token=..."]`, `"q":"?token=..."`),
 * so the secret landed in the HTML document body — CDN cache, view-source,
 * HAR bodies.
 *
 * Transport now: `src/proxy.ts` strips `token` from the query on embed routes
 * and forwards it as the `x-embed-token` request header on an internal
 * rewrite. The browser URL keeps `?token=` (the client still reads it there,
 * so no client change was needed), but the render never sees it. The header
 * is the same `x-embed-token` the tenant-config and chat API routes already
 * authenticate on — one header name for the secret on every server path.
 */

export const EMBED_TOKEN_QUERY_PARAM = "token";
export const EMBED_TOKEN_HEADER = "x-embed-token";

/** First value wins, matching the embed shell's existing `first()` helper. */
export function firstQueryValue(
  value: string | string[] | null | undefined,
): string | undefined {
  if (value === null || value === undefined) return undefined;
  return Array.isArray(value) ? value[0] : value;
}

/**
 * Resolve the embed token for the server render. The proxy-forwarded header
 * wins; the query param remains as fallback for direct hits that bypassed
 * the proxy (and for tests). Empty/whitespace-only values resolve to
 * undefined on both arms.
 */
export function resolveEmbedRenderToken(input: {
  headerToken?: string | null;
  queryToken?: string | string[] | null;
}): string | undefined {
  const header = input.headerToken?.trim();
  if (header) return header;
  const query = firstQueryValue(input.queryToken)?.trim();
  return query || undefined;
}

/**
 * Split a request URL into the token (if any) and the tokenless URL. Pure
 * helper behind the proxy rewrite; unit-tested, no Next.js dependency.
 * Keeps every other param (host, mode, theme, ...) untouched.
 */
export function stripEmbedTokenFromUrl(rawUrl: string): {
  token: string | undefined;
  cleanUrl: string;
} {
  const url = new URL(rawUrl);
  const raw = url.searchParams.get(EMBED_TOKEN_QUERY_PARAM);
  url.searchParams.delete(EMBED_TOKEN_QUERY_PARAM);
  const token = raw?.trim() || undefined;
  return { token, cleanUrl: url.toString() };
}
