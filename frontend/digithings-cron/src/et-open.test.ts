import { describe, expect, it } from "vitest";
import {
  AT_OPEN_EDT_CRON,
  AT_OPEN_EST_CRON,
  isAtOrAfterEtOpen,
  shouldDispatchAtOpen,
} from "./et-open";

describe("isAtOrAfterEtOpen", () => {
  // EST (UTC-5): 2026-01-15 — 09:30 ET = 14:30 UTC
  it("admits exactly 09:30 EST", () => {
    expect(isAtOrAfterEtOpen(Date.UTC(2026, 0, 15, 14, 30, 0))).toBe(true);
  });

  it("rejects 09:29 EST", () => {
    expect(isAtOrAfterEtOpen(Date.UTC(2026, 0, 15, 14, 29, 0))).toBe(false);
  });

  it("admits mid-morning EST", () => {
    expect(isAtOrAfterEtOpen(Date.UTC(2026, 0, 15, 15, 0, 0))).toBe(true);
  });

  // EDT (UTC-4): 2026-07-15 — 09:30 ET = 13:30 UTC
  it("admits exactly 09:30 EDT", () => {
    expect(isAtOrAfterEtOpen(Date.UTC(2026, 6, 15, 13, 30, 0))).toBe(true);
  });

  it("rejects 09:29 EDT", () => {
    expect(isAtOrAfterEtOpen(Date.UTC(2026, 6, 15, 13, 29, 0))).toBe(false);
  });

  it("admits afternoon EDT", () => {
    expect(isAtOrAfterEtOpen(Date.UTC(2026, 6, 15, 18, 0, 0))).toBe(true);
  });

  // Dual at-open UTC slots: 13:40 UTC is 08:40 EST (reject) / 09:40 EDT (admit)
  it("rejects 13:40 UTC in EST (before open)", () => {
    expect(isAtOrAfterEtOpen(Date.UTC(2026, 0, 15, 13, 40, 0))).toBe(false);
  });

  it("admits 13:40 UTC in EDT (after open)", () => {
    expect(isAtOrAfterEtOpen(Date.UTC(2026, 6, 15, 13, 40, 0))).toBe(true);
  });

  it("admits exactly one seasonal cron in EST", () => {
    const when = Date.UTC(2026, 0, 15, 14, 40, 0);
    expect(shouldDispatchAtOpen(AT_OPEN_EST_CRON, when)).toBe(true);
    expect(shouldDispatchAtOpen(AT_OPEN_EDT_CRON, when)).toBe(false);
  });

  it("admits exactly one seasonal cron in EDT", () => {
    const when = Date.UTC(2026, 6, 15, 13, 40, 0);
    expect(shouldDispatchAtOpen(AT_OPEN_EDT_CRON, when)).toBe(true);
    expect(shouldDispatchAtOpen(AT_OPEN_EST_CRON, when)).toBe(false);
  });
});
