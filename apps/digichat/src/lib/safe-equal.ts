import { timingSafeEqual } from "node:crypto";

/**
 * Constant-time comparison of two UTF-8 strings, for secret material.
 *
 * `timingSafeEqual` throws on a length mismatch, so the lengths are compared
 * first and the call is only made on equal-length buffers. The length of a
 * credential is not itself secret here.
 *
 * Three modules under `src/lib` carried a private copy of this helper: the
 * machine-key check, the monitor-token allowlist and the session-link token
 * comparison. They now share this one, so a future change to how these are
 * compared cannot be applied to one caller and missed in another.
 */
export function safeEqualStr(a: string, b: string): boolean {
  const ba = Buffer.from(a, "utf8");
  const bb = Buffer.from(b, "utf8");
  if (ba.length !== bb.length) return false;
  return timingSafeEqual(ba, bb);
}
