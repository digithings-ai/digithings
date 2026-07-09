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

/**
 * Dev tooling (Next.js HMR / React Refresh) evaluates code via eval() and
 * needs 'unsafe-eval' in script-src. Added ONLY outside production so the
 * shipped CSP stays byte-identical; mirrors the localhost dev-guard on
 * embedFrameAncestors below. Evaluated at import — next dev loads this config
 * with NODE_ENV=development, next build with NODE_ENV=production. (#1434)
 */
const SCRIPT_SRC_DEV_EVAL = process.env.NODE_ENV !== "production" ? " 'unsafe-eval'" : "";

/** Baseline CSP for the authenticated app (frame-ancestors deny). */
export const DIGICHAT_APP_CSP = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${SCRIPT_SRC_DEV_EVAL}`,
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

/** Plain comma-separated hostnames — no secrets, safe to pass as a build arg. */
function embedHostsFromEnv(): string[] | null {
  const raw = process.env.DIGICHAT_EMBED_HOSTS?.trim();
  if (!raw) return null;
  return raw
    .split(",")
    .map((h) => h.trim())
    .filter(Boolean);
}

/**
 * First-party origins + one https origin per registered embed-tenant host.
 * Dev/test additionally allow localhost so a local page can iframe /embed.
 * Evaluated when next.config.ts imports this module — some source of embed
 * hosts must be set at build time for external hosts to appear in the CSP.
 * Prefers the non-secret DIGICHAT_EMBED_HOSTS (just hostnames) over the full
 * DIGICHAT_EMBED_TENANTS registry (hostname + per-tenant token), since a
 * Docker build-arg persists in image layer history and cloud-build logs —
 * the token was never actually read here, only the registry's keys were.
 */
export function embedFrameAncestors(): string[] {
  const envHosts = embedHostsFromEnv();
  const hosts = envHosts ?? [...getEmbedTenantRegistry().keys()];
  const hostOrigins = hosts.map((h) => `https://${h}`);
  const dev =
    process.env.NODE_ENV !== "production" ? ["http://localhost:*", "http://127.0.0.1:*"] : [];
  return [...FIRST_PARTY_FRAME_ANCESTORS, ...hostOrigins, ...dev];
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
