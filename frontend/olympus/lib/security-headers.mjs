/**
 * Static-export security headers for Olympus (REM-077).
 * Canonical values — mirrored in `frontend/digiquant-web/public/_headers`, which
 * scripts/build-digiquant.sh copies to the dist ROOT (Cloudflare Pages ignores
 * _headers files below the output root, so a copy under dist/olympus/ would
 * never apply in production — #674).
 */

export const OLYMPUS_CSP = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob: https:",
  "font-src 'self' data:",
  "connect-src 'self' https://*.supabase.co",
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "object-src 'none'",
].join("; ");

export const OLYMPUS_SECURITY_HEADERS = [
  { key: "Content-Security-Policy", value: OLYMPUS_CSP },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  {
    key: "Permissions-Policy",
    value: "camera=(), microphone=(), geolocation=()",
  },
];
