/**
 * Security response headers for digichat (REM-077).
 * App CSP is baked via `next.config.ts`. `/embed` frame-ancestors are set at
 * request time by `src/proxy.ts` from runtime env — next.config only bakes
 * fail-closed `frame-ancestors 'none'` so a missing proxy cannot open framing.
 */

import { getEmbedTenantRegistry, normalizeEmbedHost } from "./embed-tenants";

const FIRST_PARTY_FRAME_ANCESTORS = [
  "'self'",
  "https://digithings.ai",
  "https://www.digithings.ai",
  "https://digiquant.io",
] as const;

/**
 * Dev tooling (Next.js HMR / React Refresh) evaluates code via eval() and
 * needs 'unsafe-eval' in script-src. Added ONLY outside production so the
 * shipped CSP stays byte-identical; mirrors the localhost dev-guard on
 * embedFrameAncestors below. Evaluated at import — next dev loads this config
 * with NODE_ENV=development, next build with NODE_ENV=production. (#1434)
 * Note: 'unsafe-eval' is a CSP token string only — not JavaScript eval().
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

/** Baked into next.config `/embed` headers — proxy overwrites at request time. */
export const DIGICHAT_EMBED_FAIL_CLOSED_CSP = "frame-ancestors 'none';";

/** Valid hostnames only — never `*`, never empty. */
export function parseEmbedHostsEnv(raw: string | undefined): string[] {
  if (!raw?.trim()) return [];
  const out: string[] = [];
  for (const part of raw.split(",")) {
    const host = normalizeEmbedHost(part);
    if (!host) continue;
    if (host === "*" || host.includes("*")) continue;
    out.push(host);
  }
  return out;
}

/**
 * Plain comma-separated hostnames — no secrets.
 * Returns null when the env var is unset/blank (fall back to registry).
 * Returns [] when set but every token is invalid (no customer hosts; no registry fallback).
 */
function embedHostsFromEnv(): string[] | null {
  const raw = process.env.DIGICHAT_EMBED_HOSTS;
  if (raw === undefined || !raw.trim()) return null;
  return parseEmbedHostsEnv(raw);
}

/**
 * First-party origins + https origins for customer embed parents.
 * Re-reads `process.env` every call so runtime DIGICHAT_EMBED_HOSTS /
 * DIGICHAT_EMBED_TENANTS work on the stock GHCR image without rebuild.
 * Prefers DIGICHAT_EMBED_HOSTS when set; otherwise registry host keys.
 * Never emits bare `*` or wildcard host tokens.
 */
export function embedFrameAncestors(): string[] {
  const envParsed = embedHostsFromEnv();
  // If DIGICHAT_EMBED_HOSTS is set (even empty after filter), do not fall back to registry.
  // If unset (null), fall back to registry keys.
  const hosts =
    envParsed !== null ? envParsed : [...getEmbedTenantRegistry().keys()];
  const hostOrigins = hosts
    .map((h) => normalizeEmbedHost(h))
    .filter((h): h is string => !!h && h !== "*" && !h.includes("*"))
    .map((h) => `https://${h}`);
  const dev =
    process.env.NODE_ENV !== "production"
      ? ["http://localhost:*", "http://127.0.0.1:*"]
      : [];
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

/** Fail-closed bake for next.config — proxy sets the real allowlist at request time. */
export const DIGICHAT_EMBED_BAKED_SECURITY_HEADERS: ReadonlyArray<{
  key: string;
  value: string;
}> = [
  { key: "Content-Security-Policy", value: DIGICHAT_EMBED_FAIL_CLOSED_CSP },
  { key: "X-Content-Type-Options", value: "nosniff" },
];

/**
 * @deprecated Use DIGICHAT_EMBED_BAKED_SECURITY_HEADERS in next.config and
 * embedFrameAncestorsCsp() from proxy. Kept for transitional test imports.
 */
export const DIGICHAT_EMBED_SECURITY_HEADERS: ReadonlyArray<{
  key: string;
  value: string;
}> = DIGICHAT_EMBED_BAKED_SECURITY_HEADERS;
