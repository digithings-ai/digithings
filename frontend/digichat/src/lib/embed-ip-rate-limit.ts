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
import { isIP } from "node:net";

export const EMBED_IP_MAX = envPositiveInt("DIGICHAT_EMBED_IP_RATE_LIMIT_MAX", 10);
const EMBED_IP_WINDOW_MS = envPositiveInt("DIGICHAT_EMBED_IP_RATE_LIMIT_WINDOW_MS", 60_000);

type ParsedIp = { bytes: number[]; version: 4 | 6 };
type TrustedNetwork = ParsedIp & { prefix: number };

function parseIp(value: string): ParsedIp | null {
  const version = isIP(value);
  if (version === 4) {
    const bytes = value.split(".").map(Number);
    return { bytes, version: 4 };
  }
  if (version !== 6) return null;

  const [before, after = ""] = value.toLowerCase().split("::");
  if (value.split("::").length > 2) return null;
  const expand = (part: string): string[] => (part ? part.split(":") : []);
  const parts = [...expand(before), ...expand(after)];
  const ipv4Part = parts.at(-1);
  if (ipv4Part?.includes(".")) {
    const ipv4 = parseIp(ipv4Part);
    if (!ipv4 || ipv4.version !== 4) return null;
    parts.splice(-1, 1, ((ipv4.bytes[0]! << 8) | ipv4.bytes[1]!).toString(16));
    parts.push(((ipv4.bytes[2]! << 8) | ipv4.bytes[3]!).toString(16));
  }
  if (parts.length > 8 || (!value.includes("::") && parts.length !== 8)) return null;
  const hextets = [
    ...expand(before),
    ...Array(8 - parts.length).fill("0"),
    ...expand(after),
  ].flatMap((part) => {
    if (part.includes(".")) {
      const ipv4 = parseIp(part);
      return ipv4?.version === 4
        ? [
            ((ipv4.bytes[0]! << 8) | ipv4.bytes[1]!).toString(16),
            ((ipv4.bytes[2]! << 8) | ipv4.bytes[3]!).toString(16),
          ]
        : [];
    }
    return [part];
  });
  if (hextets.length !== 8 || hextets.some((part) => !/^[\da-f]{1,4}$/i.test(part))) return null;

  const bytes = hextets.flatMap((part) => {
    const value = Number.parseInt(part, 16);
    return [value >> 8, value & 0xff];
  });
  const isIpv4Mapped = bytes.slice(0, 10).every((byte) => byte === 0) && bytes[10] === 0xff && bytes[11] === 0xff;
  return isIpv4Mapped ? { bytes: bytes.slice(12), version: 4 } : { bytes, version: 6 };
}

function parseTrustedProxies(raw: string): TrustedNetwork[] {
  return raw.split(",").flatMap((entry) => {
    const [address, prefixText, ...extra] = entry.trim().split("/");
    if (!address || prefixText === "" || extra.length > 0) return [];
    const parsed = parseIp(address);
    const prefix = prefixText === undefined ? (parsed?.version === 4 ? 32 : 128) : Number(prefixText);
    if (!parsed || !Number.isInteger(prefix) || prefix < 0 || prefix > parsed.bytes.length * 8) return [];
    return [{ ...parsed, prefix }];
  });
}

function isTrusted(ip: string, networks: TrustedNetwork[]): boolean {
  const parsed = parseIp(ip);
  if (!parsed) return false;
  return networks.some((network) => {
    if (network.version !== parsed.version) return false;
    const fullBytes = Math.floor(network.prefix / 8);
    const remainingBits = network.prefix % 8;
    if (network.bytes.slice(0, fullBytes).some((byte, index) => byte !== parsed.bytes[index])) return false;
    if (remainingBits === 0) return true;
    const mask = (0xff << (8 - remainingBits)) & 0xff;
    return (network.bytes[fullBytes]! & mask) === (parsed.bytes[fullBytes]! & mask);
  });
}

function forwardedIp(req: Request, networks: TrustedNetwork[]): string | null {
  const cf = req.headers.get("cf-connecting-ip")?.trim();
  if (cf && parseIp(cf)) return cf;

  const hops = req.headers
    .get("x-forwarded-for")
    ?.split(",")
    .map((hop) => hop.trim())
    .filter(Boolean);
  if (!hops) return null;
  for (const hop of hops.reverse()) {
    if (isTrusted(hop, networks)) continue;
    return parseIp(hop) ? hop : null;
  }
  return null;
}

/**
 * Best-effort client IP for rate-limiting only — never treat this as an
 * identity signal. `cf-connecting-ip` is set authoritatively by Cloudflare's
 * edge (digichat's deployment target per ADR-0018) and can't be spoofed by
 * the client when actually behind Cloudflare. Falls back to the first
 * `X-Forwarded-For` hop for non-Cloudflare setups (dev, other proxies) — that
 * header, and `cf-connecting-ip` itself outside Cloudflare, CAN be spoofed
 * absent a proxy that strips/overwrites them. When `DIGICHAT_TRUSTED_PROXIES`
 * is configured, only a socket peer captured by the production entrypoint in
 * `x-digichat-peer-ip` can authorize using either forwarded header. That
 * internal header is removed and re-added from `socket.remoteAddress` before
 * Next.js receives a request, so callers cannot forge it.
 */
export function clientIpForRateLimit(req: Request): string {
  const trustedRaw = process.env.DIGICHAT_TRUSTED_PROXIES ?? "";
  const trustedProxies = parseTrustedProxies(trustedRaw);
  if (trustedRaw.trim()) {
    const peer = req.headers.get("x-digichat-peer-ip")?.trim();
    if (!peer || !isTrusted(peer, trustedProxies)) return peer || "unknown";
    return forwardedIp(req, trustedProxies) ?? peer;
  }
  const cf = req.headers.get("cf-connecting-ip")?.trim();
  if (cf) return cf;
  const xff = req.headers.get("x-forwarded-for");
  if (xff) return xff.split(",")[0]?.trim() || "unknown";
  return "unknown";
}

/** Per-IP check for the shared anonymous /embed chat bucket. */
export function checkEmbedIpRateLimit(
  req: Request
): { allowed: true } | { allowed: false; retryAfterSec: number } {
  const ip = clientIpForRateLimit(req);
  return checkBffRateLimit(`embed_ip:${ip}`, EMBED_IP_MAX, EMBED_IP_WINDOW_MS);
}
