import { describe, expect, it } from "vitest";
import { checkBffRateLimit } from "@/lib/bff-rate-limit";

describe("checkBffRateLimit", () => {
  it("allows requests under the limit", () => {
    const key = `test-${Date.now()}`;
    expect(checkBffRateLimit(key, 3, 60_000).allowed).toBe(true);
    expect(checkBffRateLimit(key, 3, 60_000).allowed).toBe(true);
    expect(checkBffRateLimit(key, 3, 60_000).allowed).toBe(true);
  });

  it("blocks when limit exceeded", () => {
    const key = `block-${Date.now()}`;
    for (let i = 0; i < 2; i++) {
      expect(checkBffRateLimit(key, 2, 60_000).allowed).toBe(true);
    }
    const blocked = checkBffRateLimit(key, 2, 60_000);
    expect(blocked.allowed).toBe(false);
    if (!blocked.allowed) {
      expect(blocked.retryAfterSec).toBeGreaterThan(0);
    }
  });
});
