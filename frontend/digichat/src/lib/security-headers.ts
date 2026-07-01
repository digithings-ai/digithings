/**
 * Security response headers for DigiChat (REM-077).
 * Consumed by `next.config.ts` — keep in sync with README / ARCHITECTURE.
 */

export const EMBED_FRAME_ANCESTORS = [
  "'self'",
  "https://digithings.ai",
  "https://digiquant.io",
] as const;

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

export function embedFrameAncestorsCsp(): string {
  return `frame-ancestors ${EMBED_FRAME_ANCESTORS.join(" ")};`;
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
