import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { embedFrameAncestorsCsp } from "./lib/security-headers";

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
  const response = NextResponse.next();
  const { pathname, searchParams } = request.nextUrl;
  const isEmbedPath =
    pathname === "/embed" || pathname.startsWith("/embed/");
  const isEmbedMode =
    pathname === "/" && searchParams.get("mode") === "embed";
  if (!isEmbedPath && !isEmbedMode) return response;
  // Overwrite baked fail-closed CSP from next.config (do not append a second policy).
  response.headers.set(
    "Content-Security-Policy",
    embedFrameAncestorsCsp(),
  );
  response.headers.set("X-Content-Type-Options", "nosniff");
  if (isEmbedMode) {
    // Baked app headers (applied to `/` by next.config) deny framing and
    // allow caching — both wrong for per-tenant embed HTML.
    response.headers.delete("X-Frame-Options");
    response.headers.set("Cache-Control", "no-store");
  }
  return response;
}

export const config = {
  matcher: ["/embed", "/embed/:path*", "/"],
};
