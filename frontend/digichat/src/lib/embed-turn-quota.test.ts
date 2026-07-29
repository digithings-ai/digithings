import { afterEach, describe, expect, it, vi } from "vitest";
import {
  recordEmbedTrialTurn,
  isOverEmbedTrialLimit,
  unlockEmbedTrial,
  resetEmbedTrialQuotaForTests,
} from "@/lib/embed-turn-quota";
import { EMBED_FREE_TURN_LIMIT, EMBED_TRIAL_SERVER_TURN_LIMIT } from "@/lib/embed-turn-limits";

afterEach(() => {
  resetEmbedTrialQuotaForTests();
  vi.useRealTimers();
});

describe("embed-turn-quota", () => {
  it(`allows the first ${EMBED_TRIAL_SERVER_TURN_LIMIT} turns, then reports over-limit on the next`, () => {
    const ip = "1.2.3.4";
    for (let i = 0; i < EMBED_TRIAL_SERVER_TURN_LIMIT; i++) {
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

  it("seeds the server cap looser than the client-advertised free limit, so shared egress (NAT/CGNAT) isn't punished while a localStorage bypasser is still eventually caught", () => {
    expect(EMBED_TRIAL_SERVER_TURN_LIMIT).toBeGreaterThan(EMBED_FREE_TURN_LIMIT);
    // The client cap alone (3 turns) must NOT trip the server-side gate —
    // that's exactly the "4th visitor on a shared IP" scenario this looser
    // cap exists to protect.
    const ip = "5.6.7.8";
    for (let i = 0; i < EMBED_FREE_TURN_LIMIT; i++) recordEmbedTrialTurn(ip);
    expect(isOverEmbedTrialLimit(ip)).toBe(false);
  });

  it("unlock raises the cap so counting continues past the server limit", () => {
    const ip = "1.2.3.4";
    for (let i = 0; i < EMBED_TRIAL_SERVER_TURN_LIMIT; i++) recordEmbedTrialTurn(ip);
    expect(isOverEmbedTrialLimit(ip)).toBe(true);
    unlockEmbedTrial(ip);
    expect(isOverEmbedTrialLimit(ip)).toBe(false);
  });

  it("counts each IP independently", () => {
    for (let i = 0; i < EMBED_TRIAL_SERVER_TURN_LIMIT; i++) recordEmbedTrialTurn("a");
    recordEmbedTrialTurn("b");
    expect(isOverEmbedTrialLimit("a")).toBe(true);
    expect(isOverEmbedTrialLimit("b")).toBe(false);
  });

  it("evicts entries after the TTL so a stale IP starts fresh", () => {
    vi.useFakeTimers();
    const ip = "1.2.3.4";
    for (let i = 0; i < EMBED_TRIAL_SERVER_TURN_LIMIT; i++) recordEmbedTrialTurn(ip);
    expect(isOverEmbedTrialLimit(ip)).toBe(true);
    vi.advanceTimersByTime(24 * 60 * 60_000 + 1_000);
    expect(isOverEmbedTrialLimit(ip)).toBe(false);
  });
});
