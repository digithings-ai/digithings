/** Sliding-window rate limit for BFF routes (per user sub). */

import { BoundedTTLMap } from "@/lib/bounded-map";

type Window = { timestamps: number[] };

const MAX_RATE_LIMIT_KEYS = 10_000;
const windows = new BoundedTTLMap<string, Window>(MAX_RATE_LIMIT_KEYS, 60 * 60_000);

const DEFAULT_MAX = Number(process.env.DIGICHAT_CHAT_RATE_LIMIT_MAX ?? "30");
const DEFAULT_WINDOW_MS = Number(process.env.DIGICHAT_CHAT_RATE_LIMIT_WINDOW_MS ?? "60_000");

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
