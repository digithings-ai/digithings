import { afterEach, describe, expect, it, vi } from "vitest";
import { checkBffRateLimit, envPositiveInt } from "@/lib/bff-rate-limit";

afterEach(() => {
  delete process.env.DIGICHAT_TEST_ENV_POSITIVE_INT;
  vi.restoreAllMocks();
});

describe("envPositiveInt", () => {
  it("returns fallback when unset or blank", () => {
    delete process.env.DIGICHAT_TEST_ENV_POSITIVE_INT;
    expect(envPositiveInt("DIGICHAT_TEST_ENV_POSITIVE_INT", 42)).toBe(42);
    process.env.DIGICHAT_TEST_ENV_POSITIVE_INT = "   ";
    expect(envPositiveInt("DIGICHAT_TEST_ENV_POSITIVE_INT", 42)).toBe(42);
  });

  it("rejects underscore separators that parse as NaN (#675)", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    process.env.DIGICHAT_TEST_ENV_POSITIVE_INT = "60_000";
    expect(envPositiveInt("DIGICHAT_TEST_ENV_POSITIVE_INT", 60_000)).toBe(60_000);
    expect(warn).toHaveBeenCalled();
  });

  it("rejects zero, negative, and non-integer values", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    for (const raw of ["0", "-1", "3.5", "abc"]) {
      process.env.DIGICHAT_TEST_ENV_POSITIVE_INT = raw;
      expect(envPositiveInt("DIGICHAT_TEST_ENV_POSITIVE_INT", 7)).toBe(7);
    }
    expect(warn.mock.calls.length).toBeGreaterThanOrEqual(4);
  });

  it("accepts a plain positive integer string", () => {
    process.env.DIGICHAT_TEST_ENV_POSITIVE_INT = "90";
    expect(envPositiveInt("DIGICHAT_TEST_ENV_POSITIVE_INT", 7)).toBe(90);
  });
});

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
