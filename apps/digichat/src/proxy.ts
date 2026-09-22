import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { embedFrameAncestorsCsp } from "./lib/security-headers";

/**
 * Next 16 Proxy (renamed from middleware). Owns `/embed` CSP at request time
 * so stock GHCR images can admit new parents via runtime DIGICHAT_EMBED_HOSTS
 * / DIGICHAT_EMBED_TENANTS without rebuild. Overwrites the fail-closed bake
 * from next.config (do not append a second CSP — browsers intersect them).
 */
export function proxy(request: NextRequest) {
  void request;
  const response = NextResponse.next();
  // Overwrite baked fail-closed CSP from next.config (do not append a second policy).
  response.headers.set("Content-Security-Policy", embedFrameAncestorsCsp());
  response.headers.set("X-Content-Type-Options", "nosniff");
  return response;
}

export const config = {
  matcher: ["/embed", "/embed/:path*"],
};
