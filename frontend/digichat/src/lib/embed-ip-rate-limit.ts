/**
 * Per-IP sliding-window limiter for the anonymous /embed chat surface (#1251).
 *
 * `checkBffRateLimit`'s shared bucket keys on `chat:embed:embed:anonymous` —
 * every unauthenticated embed visitor combined. This sits in front of that
 * check so one visitor can't exhaust the shared quota for everyone, mirroring
 * `frontend/digithings-web/functions/api/chat.ts`'s per-IP `rateLimit()`.
 *
 * INVARIANT: the per-IP max here must stay below `DIGICHAT_CHAT_RATE_LIMIT_MAX`
 * (the shared bucket's cap, default 30/min in bff-rate-limit.ts). If it isn't,
 * one visitor hits the *shared* bucket's ceiling before ever tripping this
 * per-IP one — the per-IP layer becomes a no-op and the exact abuse this
 * exists to prevent (one visitor exhausting the shared quota) still happens.
 * A caught-in-review regression (#1251): the first cut of this file defaulted
 * to 60/min here against the shared default of 30/min.
 */

import { checkBffRateLimit, envPositiveInt } from "@/lib/bff-rate-limit";

export const EMBED_IP_MAX = envPositiveInt("DIGICHAT_EMBED_IP_RATE_LIMIT_MAX", 10);
const EMBED_IP_WINDOW_MS = envPositiveInt("DIGICHAT_EMBED_IP_RATE_LIMIT_WINDOW_MS", 60_000);

/**
 * Best-effort client IP for rate-limiting only — never treat this as an
 * identity signal. `cf-connecting-ip` is set authoritatively by Cloudflare's
 * edge (DigiChat's deployment target per ADR-0018) and can't be spoofed by
 * the client when actually behind Cloudflare. Falls back to the first
 * `X-Forwarded-For` hop for non-Cloudflare setups (dev, other proxies) — that
 * header, and `cf-connecting-ip` itself outside Cloudflare, CAN be spoofed
 * absent a proxy that strips/overwrites them. DigiGraph closed the equivalent
 * gap in its own rate limiter via a `DIGI_TRUSTED_PROXIES` allowlist
 * (digigraph/ARCHITECTURE.md §12.8, REM-027); this module has no equivalent
 * yet (tracked as a follow-up) — acceptable only because this is a
 * rate-limiting decision, not an authorization one.
 */
export function clientIpForRateLimit(req: Request): string {
  const cf = req.headers.get("cf-connecting-ip")?.trim();
  if (cf) return cf;
  const xff = req.headers.get("x-forwarded-for");
  if (xff) {
    const first = xff.split(",")[0]?.trim();
    if (first) return first;
  }
  return "unknown";
}

/** Per-IP check for the shared anonymous /embed chat bucket. */
export function checkEmbedIpRateLimit(
  req: Request
): { allowed: true } | { allowed: false; retryAfterSec: number } {
  const ip = clientIpForRateLimit(req);
  return checkBffRateLimit(`embed_ip:${ip}`, EMBED_IP_MAX, EMBED_IP_WINDOW_MS);
}
