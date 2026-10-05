import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { expectedCount } from "./expected";

/**
 * `expectedCount` falls back to `new Date()` when the caller passes no `now`,
 * and it clamps the count to the minutes already due whenever the queried day
 * is the day that clock reports (the `cutoff` in `expected.ts`). An assertion
 * that omits `now` is therefore only correct by accident: it holds for part of
 * the year and fails the rest of it, which is what made this suite a lottery.
 *
 * `count` below makes the clock a required argument, so no case can reach that
 * fallback. The clamp itself is the cron monitor's real contract, so it keeps
 * its own cases rather than being removed.
 */
function count(cron: string, day: string, now: string): number {
  return expectedCount(cron, day, { now: new Date(now) });
}

describe("expectedCount", () => {
  it("A.7 an hourly weekday clock owes 24 starts on a Monday", () => {
    expect(count("52 * * * MON-FRI", "2026-09-28", "2026-09-29T00:00:00Z")).toBe(24);
  });
  it("A.7 the same clock owes nothing on a Sunday", () => {
    expect(count("52 * * * MON-FRI", "2026-09-27", "2026-09-28T00:00:00Z")).toBe(0);
  });
  it("counts hour lists and step syntax", () => {
    // 06:03 and 18:03, and every fourth hour from midnight.
    expect(count("3 6,18 * * *", "2026-10-05", "2026-10-06T00:00:00Z")).toBe(2);
    expect(count("4 */4 * * *", "2026-10-05", "2026-10-06T00:00:00Z")).toBe(6);
  });
  it("counts a day-of-month rule", () => {
    expect(count("0 0 15 * *", "2026-10-15", "2026-10-16T00:00:00Z")).toBe(1);
    expect(count("0 0 15 * *", "2026-10-16", "2026-10-17T00:00:00Z")).toBe(0);
  });

  it("counts only the minutes already due on the day in progress", () => {
    expect(count("52 * * * MON-FRI", "2026-10-05", "2026-10-05T10:00:00Z")).toBe(10);
  });

  it("clamps a day in progress to the fires already due", () => {
    // 00:30 UTC: the 06:03 fire has not happened yet, so nothing is owed.
    expect(count("3 6,18 * * *", "2026-10-05", "2026-10-05T00:30:00Z")).toBe(0);
    // 07:00 UTC: 06:03 is due, 18:03 is not.
    expect(count("3 6,18 * * *", "2026-10-05", "2026-10-05T07:00:00Z")).toBe(1);
    // 18:03 UTC exactly is still "not yet", because the cutoff is exclusive.
    expect(count("3 6,18 * * *", "2026-10-05", "2026-10-05T18:03:00Z")).toBe(1);
    // 18:04 UTC: both fires are due.
    expect(count("3 6,18 * * *", "2026-10-05", "2026-10-05T18:04:00Z")).toBe(2);
  });

  it("counts a finished day in full whatever the clock says", () => {
    // A day already past is never clamped, so an early clock on the day after
    // and a late one two days later agree.
    expect(count("3 6,18 * * *", "2026-10-04", "2026-10-05T00:30:00Z")).toBe(2);
    expect(count("3 6,18 * * *", "2026-10-04", "2026-10-06T09:00:00Z")).toBe(2);
  });

  // The guard against the class of bug this file was filed for. The suite clock
  // is pinned to 03:40 on a day two whole-day cases query, and to an instant
  // before the first fire of `3 6,18 * * *`. Any case that reaches `new Date()`
  // therefore gets a fixed, known answer instead of the real wall clock, so the
  // suite cannot pass or fail on the hour CI happens to run.
  describe("the suite clock cannot leak into an assertion", () => {
    beforeEach(() => {
      vi.useFakeTimers();
      vi.setSystemTime(new Date("2026-10-05T03:40:00Z"));
    });
    afterEach(() => {
      vi.useRealTimers();
    });

    it("pins the ambient clock", () => {
      expect(new Date().toISOString()).toBe("2026-10-05T03:40:00.000Z");
    });

    it("gives an unpinned call a fixed answer, so the old assertion would fail here", () => {
      // The exact call the old suite made, at the pinned clock: 0, not the 2 it
      // asserted. This is the lottery, made visible and no longer time-dependent.
      expect(expectedCount("3 6,18 * * *", "2026-10-05")).toBe(0);
    });

    it("still counts the whole day when a case passes its own clock", () => {
      // The same day and cron, given a clock on a day it does not query.
      expect(count("3 6,18 * * *", "2026-10-05", "2026-10-06T00:00:00Z")).toBe(2);
    });
  });
});