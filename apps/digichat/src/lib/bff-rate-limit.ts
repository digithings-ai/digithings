/** Sliding-window rate limit for BFF routes (per user sub). */

import { BoundedTTLMap } from "@/lib/bounded-map";

type Window = { timestamps: number[] };

const MAX_RATE_LIMIT_KEYS = 10_000;
const windows = new BoundedTTLMap<string, Window>(MAX_RATE_LIMIT_KEYS, 60 * 60_000);

/**
 * Parse a positive integer from the environment. `Number("60_000")` is NaN —
 * numeric separators are a literal-only syntax — and a NaN window made the
 * cutoff filter drop every timestamp, silently disabling the limiter (#675).
 */
export function envPositiveInt(name: string, fallback: number): number {
  const raw = process.env[name];
  if (raw === undefined || raw.trim() === "") return fallback;
  const parsed = Number(raw);
  if (!Number.isSafeInteger(parsed) || parsed <= 0) {
    console.warn(`bff-rate-limit: ignoring invalid ${name}=${JSON.stringify(raw)}; using ${fallback}`);
    return fallback;
  }
  return parsed;
}

export const DEFAULT_MAX = envPositiveInt("DIGICHAT_CHAT_RATE_LIMIT_MAX", 30);
const DEFAULT_WINDOW_MS = envPositiveInt("DIGICHAT_CHAT_RATE_LIMIT_WINDOW_MS", 60_000);

export function checkBffRateLimit(
  key: string,
  maxRequests: number = DEFAULT_MAX,
  windowMs: number = DEFAULT_WINDOW_MS
): { allowed: true } | { allowed: false; retryAfterSec: number } {
  const now = Date.now();
  const cutoff = now - windowMs;
  let entry = windows.get(key);
  if (!entry) {
    entry = { timestamps: [] };
  }
  entry.timestamps = entry.timestamps.filter((t) => t > cutoff);
  if (entry.timestamps.length >= maxRequests) {
    const oldest = entry.timestamps[0] ?? now;
    const retryAfterSec = Math.max(1, Math.ceil((oldest + windowMs - now) / 1000));
    return { allowed: false, retryAfterSec };
  }
  entry.timestamps.push(now);
  windows.set(key, entry, windowMs * 2);
  return { allowed: true };
}
