/**
 * Per-IP sliding-window limiter for the anonymous /embed chat surface (#1251).
 *
 * `checkBffRateLimit`'s shared bucket keys on `chat:embed:embed:anonymous` —
 * every unauthenticated embed visitor combined. This sits in front of that
 * check so one visitor can't exhaust the shared quota for everyone, mirroring
 * `apps/digithings-web/functions/api/chat.ts`'s per-IP `rateLimit()`.
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

/** A header is a rate-limit key only when `parseIp` accepts it. */
function acceptedIp(value: string | null | undefined): string | null {
  const trimmed = value?.trim();
  if (!trimmed || !parseIp(trimmed)) return null;
  return trimmed;
}

/** Header the production entrypoint sets. Callers cannot choose it. */
export const PEER_IP_HEADER = "x-digichat-peer-ip";
/** Proves `PEER_IP_HEADER` was written by this process's entrypoint. */
export const PEER_STAMP_HEADER = "x-digichat-peer-stamp";

/**
 * Logged at startup when `DIGICHAT_TRUSTED_PROXIES` is unset. The address to
 * put in that variable is the socket peer the entrypoint stamps, not a
 * Cloudflare edge range. This repo does not contain that address.
 */
export const TRUSTED_PROXIES_UNSET_WARNING =
  "DIGICHAT_TRUSTED_PROXIES is unset. The entrypoint stamps the socket peer. Guardrail and premium keys use that socket when it is the client, and unknown when it is a shared ingress. The embed limiter and trial quota follow develop: cf-connecting-ip, then the leftmost X-Forwarded-For hop, otherwise unknown. A header-less request is unknown: the embed limiter collapses onto embed_ip:unknown, and the trial quota skips it. Set DIGICHAT_TRUSTED_PROXIES to the container ingress or overlay peer the entrypoint logs, never Cloudflare's edge ranges. Spoofable headers are not guardrail or premium keys.";

export function warnTrustedProxiesUnset(
  env: NodeJS.ProcessEnv = process.env,
  log: (message: string) => void = console.warn,
): void {
  if (env.DIGICHAT_TRUSTED_PROXIES?.trim()) return;
  log(TRUSTED_PROXIES_UNSET_WARNING);
}

function stampedSocket(req: Request): string | null {
  const expected = process.env.DIGICHAT_PEER_STAMP?.trim();
  if (!expected) return null;
  const got = req.headers.get(PEER_STAMP_HEADER);
  if (!got || got !== expected) return null;
  return acceptedIp(req.headers.get(PEER_IP_HEADER));
}

/**
 * The TCP peer is a shared ingress when our entrypoint stamped it and
 * Cloudflare's visitor header names a different address. The visitor header
 * is not used as a guardrail or premium key in that case.
 */
function sharedIngress(req: Request, socket: string): boolean {
  const cf = acceptedIp(req.headers.get("cf-connecting-ip"));
  return Boolean(cf && cf !== socket);
}

function forwardedIp(req: Request, networks: TrustedNetwork[]): string | null {
  const cf = acceptedIp(req.headers.get("cf-connecting-ip"));
  if (cf) return cf;

  const hops = req.headers
    .get("x-forwarded-for")
    ?.split(",")
    .map((hop) => hop.trim())
    .filter(Boolean);
  if (!hops) return null;
  for (const hop of hops.reverse()) {
    if (isTrusted(hop, networks)) continue;
    return acceptedIp(hop);
  }
  return null;
}

/**
 * Client IP for guardrail budgets and premium spend. Never an identity.
 * Every candidate goes through `parseIp`.
 *
 * `x-digichat-peer-ip` counts only when this process's entrypoint stamped it
 * (`DIGICHAT_PEER_STAMP`). A caller-supplied copy is `"unknown"`, including
 * when `DIGICHAT_TRUSTED_PROXIES` is set. Forwarded headers
 * (`cf-connecting-ip`, `X-Forwarded-For`) count only from a stamped peer
 * that the allowlist trusts. A stamped socket that is a shared ingress is
 * also `"unknown"` here: the visitor header must not decide a guardrail or
 * premium key.
 */
export function clientIpForRateLimit(req: Request): string {
  const trustedRaw = process.env.DIGICHAT_TRUSTED_PROXIES ?? "";
  const trustedProxies = parseTrustedProxies(trustedRaw);
  const stamped = stampedSocket(req);
  if (trustedRaw.trim()) {
    if (!stamped) return "unknown";
    if (!isTrusted(stamped, trustedProxies)) return stamped;
    return forwardedIp(req, trustedProxies) ?? stamped;
  }
  if (!stamped) return "unknown";
  if (sharedIngress(req, stamped)) return "unknown";
  return stamped;
}

/**
 * develop's `clientIpForRateLimit` when `DIGICHAT_TRUSTED_PROXIES` is unset.
 * The stamped socket is not a key. The raw trimmed `cf-connecting-ip` wins,
 * then the raw trimmed first `X-Forwarded-For` hop, else `"unknown"`.
 * `parseIp` does not run: a non-IP value is still the key.
 */
function developVisitorIp(req: Request): string {
  const cf = req.headers.get("cf-connecting-ip")?.trim();
  if (cf) return cf;
  return req.headers.get("x-forwarded-for")?.split(",")[0]?.trim() || "unknown";
}

/**
 * IP for the embed per-IP limiter and the embed trial quota.
 *
 * Allowlist unset: `developVisitorIp`, the raw trimmed header. A header-less
 * request is `"unknown"`. `checkEmbedIpRateLimit` then keys
 * `embed_ip:unknown`, which is develop's collapse for that case. The trial
 * quota skips `"unknown"` and does not count those visitors together. A
 * non-IP `cf-connecting-ip` or first `X-Forwarded-For` hop is its own key.
 *
 * Allowlist set: same as `clientIpForRateLimit`. A stamped trusted peer with
 * no visitor header is that peer, which is also what develop returns.
 */
export function clientIpForEmbedLimit(req: Request): string {
  if (!(process.env.DIGICHAT_TRUSTED_PROXIES ?? "").trim()) return developVisitorIp(req);
  return clientIpForRateLimit(req);
}

/** Per-IP check for the shared anonymous /embed chat bucket. */
export function checkEmbedIpRateLimit(
  req: Request
): { allowed: true } | { allowed: false; retryAfterSec: number } {
  const ip = clientIpForEmbedLimit(req);
  return checkBffRateLimit(`embed_ip:${ip}`, EMBED_IP_MAX, EMBED_IP_WINDOW_MS);
}
