import { afterEach, describe, expect, it, vi } from "vitest";
import {
  recordEmbedTrialTurn,
  isOverEmbedTrialLimit,
  unlockEmbedTrial,
  resetEmbedTrialQuotaForTests,
} from "@/lib/embed-turn-quota";

afterEach(() => {
  resetEmbedTrialQuotaForTests();
  vi.useRealTimers();
});

describe("embed-turn-quota", () => {
  it("allows the first 3 turns, then reports over-limit on the 4th", () => {
    const ip = "1.2.3.4";
    for (let i = 0; i < 3; i++) {
      expect(isOverEmbedTrialLimit(ip)).toBe(false);
      recordEmbedTrialTurn(ip);
    }
    expect(isOverEmbedTrialLimit(ip)).toBe(true);
  });

  it("returns the running count from recordEmbedTrialTurn", () => {
    const ip = "1.2.3.4";
    expect(recordEmbedTrialTurn(ip)).toEqual({ count: 1 });
    expect(recordEmbedTrialTurn(ip)).toEqual({ count: 2 });
  });

  it("unlock raises the cap so counting continues past the free limit", () => {
    const ip = "1.2.3.4";
    for (let i = 0; i < 3; i++) recordEmbedTrialTurn(ip);
    expect(isOverEmbedTrialLimit(ip)).toBe(true);
    unlockEmbedTrial(ip);
    expect(isOverEmbedTrialLimit(ip)).toBe(false);
  });

  it("counts each IP independently", () => {
    recordEmbedTrialTurn("a");
    recordEmbedTrialTurn("a");
    recordEmbedTrialTurn("a");
    expect(isOverEmbedTrialLimit("a")).toBe(true);
    expect(isOverEmbedTrialLimit("b")).toBe(false);
  });

  it("evicts entries after the TTL so a stale IP starts fresh", () => {
    vi.useFakeTimers();
    const ip = "1.2.3.4";
    for (let i = 0; i < 3; i++) recordEmbedTrialTurn(ip);
    expect(isOverEmbedTrialLimit(ip)).toBe(true);
    vi.advanceTimersByTime(24 * 60 * 60_000 + 1_000);
    expect(isOverEmbedTrialLimit(ip)).toBe(false);
  });
});
