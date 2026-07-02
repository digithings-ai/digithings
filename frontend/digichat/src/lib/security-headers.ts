/**
 * Security response headers for DigiChat (REM-077).
 * Consumed by `next.config.ts` — keep in sync with README / ARCHITECTURE.
 */

import { getEmbedTenantRegistry } from "./embed-tenants";

const FIRST_PARTY_FRAME_ANCESTORS = [
  "'self'",
  "https://digithings.ai",
  "https://digiquant.io",
] as const;

/** @deprecated use embedFrameAncestors() instead */
export const EMBED_FRAME_ANCESTORS = FIRST_PARTY_FRAME_ANCESTORS;

/** Baseline CSP for the authenticated app (frame-ancestors deny). */
export const DIGICHAT_APP_CSP = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob: https:",
  "font-src 'self' data:",
  "connect-src 'self'",
  "frame-src 'self'",
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "object-src 'none'",
].join("; ");

/**
 * First-party origins + one https origin per registered embed-tenant host.
 * Dev/test additionally allow localhost so a local page can iframe /embed.
 * Evaluated when next.config.ts imports this module — DIGICHAT_EMBED_TENANTS
 * must be set at build time for external hosts to appear in the CSP.
 */
export function embedFrameAncestors(): string[] {
  const registryHosts = [...getEmbedTenantRegistry().keys()].map((h) => `https://${h}`);
  const dev =
    process.env.NODE_ENV !== "production" ? ["http://localhost:*", "http://127.0.0.1:*"] : [];
  return [...FIRST_PARTY_FRAME_ANCESTORS, ...registryHosts, ...dev];
}

export function embedFrameAncestorsCsp(): string {
  return `frame-ancestors ${embedFrameAncestors().join(" ")};`;
}

export const DIGICHAT_APP_SECURITY_HEADERS: ReadonlyArray<{
  key: string;
  value: string;
}> = [
  { key: "Content-Security-Policy", value: DIGICHAT_APP_CSP },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  {
    key: "Permissions-Policy",
    value: "camera=(), microphone=(), geolocation=()",
  },
];

export const DIGICHAT_EMBED_SECURITY_HEADERS: ReadonlyArray<{
  key: string;
  value: string;
}> = [
  { key: "Content-Security-Policy", value: embedFrameAncestorsCsp() },
  { key: "X-Content-Type-Options", value: "nosniff" },
];
