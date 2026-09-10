/**
 * Local-only assistant-ui baseline preview.
 * Production always 404s — this is not a public product surface.
 *
 * Default upstream is the live digithings.ai chat BFF (Cloudflare), not
 * OpenRouter and not the local research/quant graph.
 */
export const BASELINE_DEFAULT_UPSTREAM = "https://digithings.ai/api/chat";

/** Browser-like UA so Cloudflare bot fight (1010) does not block the Node proxy. */
export const BASELINE_UPSTREAM_USER_AGENT =
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36";

export function isLocalBaselinePreview(req: Request): boolean {
  if (process.env.NODE_ENV === "production") return false;
  try {
    const host = new URL(req.url).hostname;
    return host === "127.0.0.1" || host === "localhost";
  } catch {
    return false;
  }
}

/**
 * Allowlisted baseline upstream. Unknown DIGICHAT_BASELINE_UPSTREAM values
 * fall back to production (fail closed — no user-controlled SSRF).
 */
export function baselineUpstreamChatUrl(): string {
  const raw = process.env.DIGICHAT_BASELINE_UPSTREAM?.trim();
  if (!raw) return BASELINE_DEFAULT_UPSTREAM;
  try {
    const u = new URL(raw);
    if (
      u.protocol === "https:" &&
      u.hostname === "digithings.ai" &&
      u.pathname === "/api/chat"
    ) {
      return `${u.origin}${u.pathname}`;
    }
  } catch {
    /* fall through */
  }
  return BASELINE_DEFAULT_UPSTREAM;
}
