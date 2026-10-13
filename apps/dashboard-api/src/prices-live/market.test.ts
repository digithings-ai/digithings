import { describe, expect, it } from "vitest";
import {
  isExtendedUsMarketHours,
  MAX_SYMBOLS,
  MIN_REFRESH_SECONDS,
  quotedAtIso,
} from "./market";

// The rate-guard arithmetic is one decision across two constants: keep the
// product this test asserts in sync with the edge header, or re-derive both.
describe("prices-live market helpers", () => {
  it("holds the Finnhub burn-rate invariant", () => {
    // Two claims fit in any sliding 60 s window, so the ceiling is
    // 2 × MAX_SYMBOLS against the 60/min free tier.
    expect(2 * MAX_SYMBOLS).toBeLessThanOrEqual(60);
    expect(MIN_REFRESH_SECONDS).toBeLessThan(60);
  });

  it("opens during extended US hours on weekdays", () => {
    expect(isExtendedUsMarketHours(new Date("2026-08-03T14:00:00.000Z"))).toBe(true); // Mon
    expect(isExtendedUsMarketHours(new Date("2026-08-07T00:30:00.000Z"))).toBe(true); // Fri eve NY
  });

  it("closes outside the window", () => {
    expect(isExtendedUsMarketHours(new Date("2026-08-05T10:00:00.000Z"))).toBe(false); // Wed 10:00
    expect(isExtendedUsMarketHours(new Date("2026-08-08T14:00:00.000Z"))).toBe(false); // Sat
    expect(isExtendedUsMarketHours(new Date("2026-08-09T00:30:00.000Z"))).toBe(false); // Sun eve
  });

  it("treats 00:xx as the previous session day", () => {
    // 00:30 UTC Saturday is Friday evening in New York: still open.
    expect(isExtendedUsMarketHours(new Date("2026-08-08T00:30:00.000Z"))).toBe(true);
  });

  it("multiplies Finnhub seconds to ISO millis", () => {
    const fallback = new Date("2026-08-03T14:00:00.000Z");
    expect(quotedAtIso(1722600000, fallback)).toBe(new Date(1722600000 * 1000).toISOString());
  });

  it("falls back to the run clock on missing or out-of-range timestamps", () => {
    const fallback = new Date("2026-08-03T14:00:00.000Z");
    expect(quotedAtIso(null, fallback)).toBe(fallback.toISOString());
    expect(quotedAtIso(undefined, fallback)).toBe(fallback.toISOString());
    expect(quotedAtIso(0, fallback)).toBe(fallback.toISOString());
    expect(quotedAtIso(NaN, fallback)).toBe(fallback.toISOString());
    // Finite and positive, but past the JS date range: still the fallback.
    expect(quotedAtIso(1e15, fallback)).toBe(fallback.toISOString());
  });
});
