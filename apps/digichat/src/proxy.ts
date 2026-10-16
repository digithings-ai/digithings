import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { embedFrameAncestorsCsp } from "./lib/security-headers";
import {
  EMBED_TOKEN_HEADER,
  stripEmbedTokenFromUrl,
} from "./lib/embed-token-transport";

/**
 * Next 16 Proxy (renamed from middleware). Owns embed CSP at request time
 * so stock GHCR images can admit new parents via runtime DIGICHAT_EMBED_HOSTS
 * / DIGICHAT_EMBED_TENANTS without rebuild. Overwrites the fail-closed bake
 * from next.config (do not append a second CSP — browsers intersect them).
 *
 * Single-route (Step 4): the `?mode=embed` variant of `/` gets the same
 * tenant framing as `/embed`, plus `no-store` (per-tenant HTML must never
 * cache) and removal of the baked `X-Frame-Options: DENY` (browsers enforce
 * it alongside CSP — DENY would win over the allowlist). All other modes
 * (menu / product / catalog) fall through to the baked app headers.
 */
export function proxy(request: NextRequest) {
  const { pathname, searchParams } = request.nextUrl;
  const isEmbedPath =
    pathname === "/embed" || pathname.startsWith("/embed/");
  const isEmbedMode =
    pathname === "/" && searchParams.get("mode") === "embed";
  if (!isEmbedPath && !isEmbedMode) return NextResponse.next();
  // DIG-3523: keep ?token= out of the server render. Next.js serialises the
  // request URL into the flight payload ("c"/"q"), so a token in the query
  // lands in the HTML body (CDN cache, view-source, HAR). Strip it here and
  // forward it as the x-embed-token request header on an internal rewrite —
  // the browser URL (and the client, which reads ?token=) is unchanged, but
  // the render sees the tokenless URL. Empty ?token= is stripped with no
  // header set.
  let response: NextResponse;
  if (searchParams.has("token")) {
    const { token, cleanUrl } = stripEmbedTokenFromUrl(request.url);
    const requestHeaders = new Headers(request.headers);
    if (token) requestHeaders.set(EMBED_TOKEN_HEADER, token);
    response = NextResponse.rewrite(new URL(cleanUrl), {
      request: { headers: requestHeaders },
    });
  } else {
    response = NextResponse.next();
  }
  // Overwrite baked fail-closed CSP from next.config (do not append a second policy).
  response.headers.set(
    "Content-Security-Policy",
    embedFrameAncestorsCsp(),
  );
  response.headers.set("X-Content-Type-Options", "nosniff");
  if (isEmbedMode || isEmbedPath) {
    // Baked headers deny framing on `/` and allow caching — both wrong for
    // per-tenant embed HTML (`/embed` bakes only CSP/nosniff, so the delete
    // below is a no-op there). The render still varies per token (now via
    // header, see above), so both spellings need the same no-store the
    // /?mode=embed arm already had: tenant HTML must never sit in a shared
    // cache keyed by URL.
    response.headers.delete("X-Frame-Options");
    response.headers.set("Cache-Control", "no-store");
  }
  return response;
}

export const config = {
  matcher: ["/embed", "/embed/:path*", "/"],
};
