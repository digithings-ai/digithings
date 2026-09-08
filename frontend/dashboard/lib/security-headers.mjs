/**
 * Static-export security headers for the dashboard (REM-077).
 * Canonical values — mirrored in `frontend/digiquant-web/public/_headers`, which
 * scripts/build-digiquant.sh copies to the dist ROOT (Cloudflare Pages ignores
 * _headers files below the output root, so a copy under dist/dashboard/ would
 * never apply in production — #674).
 */

/**
 * digichat iframe origins for the Desk+ popup (#3422).
 * Production default is digithings.ai Containers; loopback for local dogfood.
 * Custom tunnel hosts: set NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN and extend this
 * list (or regenerate _headers) so frame-src matches.
 */
export const DASHBOARD_DIGICHAT_FRAME_SRC = [
  "'self'",
  "https://digithings.ai",
  "https://www.digithings.ai",
  "https://digichat.digithings.ai",
  "http://127.0.0.1:3005",
  "http://localhost:3005",
].join(" ");

export const DASHBOARD_CSP = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob: https:",
  "font-src 'self' data:",
  "connect-src 'self' https://*.supabase.co wss://*.supabase.co",
  `frame-src ${DASHBOARD_DIGICHAT_FRAME_SRC}`,
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "object-src 'none'",
].join("; ");

export const DASHBOARD_SECURITY_HEADERS = [
  { key: "Content-Security-Policy", value: DASHBOARD_CSP },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  {
    key: "Permissions-Policy",
    value: "camera=(), microphone=(), geolocation=()",
  },
];
