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

  it("still limits under the module defaults (regression: NaN window from '60_000')", () => {
    // Before #675 the default window parsed as NaN ("60_000" → Number → NaN,
    // numeric separators are literal-only syntax), the cutoff filter emptied
    // the history on every call, and the limiter never tripped at any volume.
    const key = `defaults-${Date.now()}`;
    let blocked = false;
    for (let i = 0; i < 100; i++) {
      if (!checkBffRateLimit(key).allowed) {
        blocked = true;
        break;
      }
    }
    expect(blocked).toBe(true);
  });
});
