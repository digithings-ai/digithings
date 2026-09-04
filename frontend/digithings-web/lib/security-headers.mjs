/**
 * digithings.ai CSP for Cloudflare Pages (`public/_headers`).
 *
 * `frame-src` must match the digichat iframe origin used by /chat
 * (`NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN`). Written at build time by
 * `write-csp-headers.mjs` (npm prebuild) so staging/tunnel hosts stay aligned.
 */

/** Same-hostname digichat Container (Worker routes /embed*). Tunnel override via env. */
export const DEFAULT_DIGICHAT_EMBED_ORIGIN = "https://digithings.ai";

/**
 * @param {NodeJS.ProcessEnv | Record<string, string | undefined>} [env]
 * @returns {string | null} absolute origin, or null if unset/invalid
 */
export function resolveDigichatEmbedOrigin(env = process.env) {
  const raw = env.NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN?.trim();
  if (!raw) return null;
  try {
    return new URL(raw).origin;
  } catch {
    return null;
  }
}

/**
 * Origin for CSP frame-src: embed env when valid, else production default.
 * @param {NodeJS.ProcessEnv | Record<string, string | undefined>} [env]
 */
export function frameSrcForCsp(env = process.env) {
  return resolveDigichatEmbedOrigin(env) ?? DEFAULT_DIGICHAT_EMBED_ORIGIN;
}

/**
 * Origin for `/chat` and `/chat/occ` iframes — same as CSP `frame-src`.
 * @param {NodeJS.ProcessEnv | Record<string, string | undefined>} [env]
 */
export function embedOriginForChat(env = process.env) {
  return frameSrcForCsp(env);
}

/**
 * @param {string} [frameSrc]
 */
export function digithingsCsp(frameSrc = frameSrcForCsp()) {
  return [
    "default-src 'self'",
    "script-src 'self' 'unsafe-inline'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: https:",
    "font-src 'self' data:",
    // OpenAPI explorer loads same-origin /openapi/*.json; swagger-ui may use a blob worker.
    "connect-src 'self' https://api.github.com",
    "worker-src 'self' blob:",
    `frame-src ${frameSrc}`,
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "object-src 'none'",
  ].join("; ");
}

/**
 * Cloudflare Pages `_headers` file body.
 * @param {string} [frameSrc]
 */
export function renderCloudflareHeaders(frameSrc = frameSrcForCsp()) {
  const csp = digithingsCsp(frameSrc);
  return [
    "# Cloudflare Pages headers for digithings.ai. Fonts are self-hosted (next/font).",
    "# /chat iframes digichat Node (digigraph). frame-src is injected at build from",
    "# NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN (default https://digithings.ai Containers).",
    "# X-Frame-Options: DENY still blocks third parties framing digithings.ai itself.",
    "/*",
    "  X-Content-Type-Options: nosniff",
    "  X-Frame-Options: DENY",
    "  Referrer-Policy: strict-origin-when-cross-origin",
    "  Permissions-Policy: camera=(), microphone=(), geolocation=()",
    `  Content-Security-Policy: ${csp}`,
    "",
  ].join("\n");
}
