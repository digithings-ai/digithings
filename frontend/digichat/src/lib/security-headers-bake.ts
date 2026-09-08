/**
 * Static CSP / security header values. next.config.ts imports this file and
 * MUST NOT import embed-tenants (or anything that pulls `@/` / thread-skins) —
 * Next's config transpile cannot resolve that graph.
 */

/**
 * Dev tooling (Next.js HMR / React Refresh) evaluates code via eval() and
 * needs 'unsafe-eval' in script-src. Added ONLY outside production so the
 * shipped CSP stays byte-identical. (#1434)
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
