import { describe, expect, it } from "vitest";
import { expectedCount } from "./expected";

// `expectedCount` clamps a queried day to the minutes already due when that day
// *is* the day `now` falls on. Every assertion below therefore passes `now`
// explicitly, so each one measures the cron rule alone and no assertion can be
// made true or false by the wall clock on the day the suite runs. The clamp has
// its own case at the bottom, which opts into it deliberately.
//
// NOT_A_QUERYED_DAY is on a day none of the assertions query, so `cutoff` is the
// full 1440 minutes and nothing is clamped. Keep it off 2026-09-27, 09-28 and
// 10-05, 10-15, 10-16 -- the days these tests name.
const NOT_A_QUERYED_DAY = new Date("2026-01-01T00:00:00Z");

describe("expectedCount", () => {
  it("A.7 an hourly weekday clock owes 24 starts on a Monday", () => {
    expect(expectedCount("52 * * * MON-FRI", "2026-09-28", { now: NOT_A_QUERYED_DAY })).toBe(24);
  });
  it("A.7 the same clock owes nothing on a Sunday", () => {
    expect(expectedCount("52 * * * MON-FRI", "2026-09-27", { now: NOT_A_QUERYED_DAY })).toBe(0);
  });
  it("counts hour lists and step syntax", () => {
    expect(expectedCount("3 6,18 * * *", "2026-10-05", { now: NOT_A_QUERYED_DAY })).toBe(2);
    expect(expectedCount("4 */4 * * *", "2026-10-05", { now: NOT_A_QUERYED_DAY })).toBe(6);
  });
  it("counts a day-of-month rule", () => {
    expect(expectedCount("0 0 15 * *", "2026-10-15", { now: NOT_A_QUERYED_DAY })).toBe(1);
    expect(expectedCount("0 0 15 * *", "2026-10-16", { now: NOT_A_QUERYED_DAY })).toBe(0);
  });
  it("counts only the minutes already due on the day in progress", () => {
    expect(
      expectedCount("52 * * * MON-FRI", "2026-10-05", { now: new Date("2026-10-05T10:00:00Z") }),
    ).toBe(10);
  });
});