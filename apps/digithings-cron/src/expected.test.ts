import { describe, expect, it } from "vitest";
import { expectedCount } from "./expected";

// Every assertion below pins `now` explicitly. A count that depends on the wall
// clock is not a contract: it goes red on a date nobody chose.
const AT = (iso: string) => new Date(iso);

describe("expectedCount", () => {
  it("A.7 an hourly weekday clock owes 24 starts on a Monday", () => {
    expect(expectedCount("52 * * * MON-FRI", "2026-09-28", { now: AT("2026-10-04T12:00:00Z") })).toBe(24);
  });
  it("A.7 the same clock owes nothing on a Sunday", () => {
    expect(expectedCount("52 * * * MON-FRI", "2026-09-27", { now: AT("2026-10-04T12:00:00Z") })).toBe(0);
  });
  // 2026-10-03 is a Saturday and it is over, so the whole day counts and no day
  // restriction applies. It sits on the Saturday that the `MON-FRI` assertion
  // above uses to prove restriction, so the pair reads as one contrast: the same
  // day owes 24 from a weekday clock and 0 from a weekday-restricted one, while
  // an unrestricted clock owes its full count on that Saturday.
  it("counts hour lists and step syntax", () => {
    expect(expectedCount("3 6,18 * * *", "2026-10-03", { now: AT("2026-10-04T12:00:00Z") })).toBe(2);
    expect(expectedCount("4 */4 * * *", "2026-10-03", { now: AT("2026-10-04T12:00:00Z") })).toBe(6);
  });
  it("counts a day-of-month rule on a day that is over", () => {
    expect(expectedCount("0 0 15 * *", "2026-10-15", { now: AT("2026-10-16T12:00:00Z") })).toBe(1);
    expect(expectedCount("0 0 15 * *", "2026-10-16", { now: AT("2026-10-16T12:00:00Z") })).toBe(0);
  });
  it("counts only the minutes already due on the day in progress", () => {
    expect(
      expectedCount("52 * * * MON-FRI", "2026-10-05", { now: AT("2026-10-05T10:00:00Z") }),
    ).toBe(10);
  });

  // A.7 boundary. The alarm compares observed starts against this number, so a
  // start that has already fired must be counted. Without this, an alarm at
  // minute :52 on a cron that fires at :52 reports 11 observed against 10 owed
  // and cries wolf every single time.
  it("counts a start that has already fired in the minute it fires", () => {
    expect(
      expectedCount("52 * * * MON-FRI", "2026-10-05", { now: AT("2026-10-05T10:52:30Z") }),
    ).toBe(11);
  });
  it("does not count a start that has not fired yet in its own minute", () => {
    expect(
      expectedCount("52 * * * MON-FRI", "2026-10-05", { now: AT("2026-10-05T10:52:00Z") }),
    ).toBe(10);
  });

  // A day that has not arrived owes nothing. Reporting the full count for a
  // future day makes a clock that will never fire look healthy.
  //
  // The last two assertions exist because the contract has to answer a harder
  // question than "is it in the future". An unrestricted clock is the case that
  // tempts an exemption, and a day later in the same month is the case that
  // tempts a month-granularity rule. Both must return 0, which pins the rule to
  // `day > today` and leaves no room for a carve-out keyed on the cron itself.
  it("owes nothing for a day that has not arrived", () => {
    expect(expectedCount("52 * * * MON-FRI", "2026-12-25", { now: AT("2026-10-04T12:00:00Z") })).toBe(0);
    expect(expectedCount("0 0 15 * *", "2026-11-15", { now: AT("2026-10-04T12:00:00Z") })).toBe(0);
    // An always-on clock owes nothing for tomorrow either.
    expect(expectedCount("3 6,18 * * *", "2026-10-05", { now: AT("2026-10-04T12:00:00Z") })).toBe(0);
    // Nor for a later day in the month that is already running.
    expect(expectedCount("3 6,18 * * *", "2026-10-20", { now: AT("2026-10-04T12:00:00Z") })).toBe(0);
  });
});

// Cloudflare schedules with Quartz, not with Vixie. The constructs below are all
// documented by Cloudflare and all of them currently parse into a plausible wrong
// number or into an empty set. A silent wrong count is worse than a refusal, so
// anything this parser does not implement exactly must throw.
describe("expectedCount rejects what it does not implement", () => {
  it.each([
    ["day-of-month L", "0 0 L * *"],
    ["day-of-month LW", "0 0 LW * *"],
    ["day-of-month 15W", "0 0 15W * *"],
    ["weekday 6L", "0 0 * * 6L"],
    ["weekday 6#3", "0 0 * * 6#3"],
    ["a numeric weekday, where Cloudflare counts 1=Sunday and 0 is rejected", "0 17 * * 7"],
    ["a step on a day field, where Cloudflare ors the field instead", "0 12 */2 * MON"],
    ["a wrapping range, where 50-59,0-5 means 384 minutes", "52 50-59,0-5 * * *"],
    ["six fields instead of five", "0 12 * * * MON-FRI"],
    ["four fields instead of five", "0 12 * *"],
    ["a minute above 59", "75 * * * *"],
    ["a day below 1", "0 0 -5 * *"],
  ])("throws on %s", (_label, cron) => {
    expect(() => expectedCount(cron, "2026-10-05", { now: AT("2026-10-05T12:00:00Z") })).toThrow(
      /unsupported/i,
    );
  });
});