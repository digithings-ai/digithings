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
// A range whose `from` is larger than its `to` is not a Quartz range at all:
// croner rejects it outright ("From value is larger than to value: '5-1'") and
// does not wrap it. The loop `for (let value = lo; value <= hi; value += step)`
// simply never runs when `lo > hi`, so the field parses to an empty set and
// expectedCount returns 0 -- a confident wrong number, where 0 reads as a day
// on which the clock never fired. Refusing is the only safe answer.
//
// Grounded in croner@9, the Quartz-compatible parser Cloudflare's cron model
// tracks. NOT grounded, and deliberately not asserted here: whether Quartz
// accepts a comma list that mixes a range with a single value (`MON-FRI,SAT`).
// croner throws an internal TypeError on that form, so the reference cannot
// answer it and this leaf does not pin a claim it cannot support.
describe("expectedCount rejects a reversed range instead of counting zero", () => {
  it.each([
    ["a reversed weekday range", "0 0 * * FRI-MON"],
    ["a reversed weekday range that starts on Saturday", "0 0 * * SAT-MON"],
    ["a reversed numeric range", "5-1 * * * *"],
  ])("throws on %s rather than returning an empty count", (_label, cron) => {
    expect(() => expectedCount(cron, "2026-10-05", { now: AT("2026-10-05T12:00:00Z") })).toThrow(
      /unsupported|range/i,
    );
  });

  // Regression guards. A reversed range must not be "fixed" by teaching the
  // parser to wrap: Quartz does not wrap, and a wrapped count would be a wrong
  // number wearing the same clothes as the bug this leaf removes.
  it("still counts a well-formed weekday range", () => {
    expect(expectedCount("0 0 * * MON-FRI", "2026-10-05", { now: AT("2026-10-05T12:00:00Z") })).toBe(1);
    expect(expectedCount("0 0 * * FRI-SAT", "2026-10-05", { now: AT("2026-10-05T12:00:00Z") })).toBe(0);
  });
  it("still counts a well-formed numeric range", () => {
    expect(expectedCount("0 9-17 * * *", "2026-10-05", { now: AT("2026-10-05T23:00:00Z") })).toBe(9);
    expect(expectedCount("0 0 * * *", "2026-10-05", { now: AT("2026-10-05T23:00:00Z") })).toBe(1);
    expect(expectedCount("0 0-23/6 * * *", "2026-10-05", { now: AT("2026-10-05T23:00:00Z") })).toBe(4);
  });
});


// `?` is the Quartz "no specific value" token. It reaches expectedCount as NaN
// (Number("?") is NaN and `at < 0` is false, so num() returns it unchanged),
// and the counting loop `for (let value = lo; value <= hi; ...)` runs zero
// times because NaN <= NaN is false. The field becomes an empty set and
// expectedCount answers 0.
//
// 0 owed is the worst answer available: .7's alarm compares observed starts
// against owed starts, so 0 reads as a healthy day on which the clock never
// fired -- indistinguishable from correct.
//
// The .1c guard cannot catch this: it tests `lo > hi`, and NaN > NaN is false.
// This is the same NaN hole one level up.
//
// REFUSING is the contract, not modelling. croner@9.1.0 does not implement
// Quartz's `?` -- it reads it as the digit 0, so `0 9 * * ?` fires weekly and
// `0 9 ? * *` never fires. There is no trustworthy reference to copy, and a
// wrong number is worse than a refusal. Refusing on `?` also makes both
// tempting wrong fixes fail: mapping `?` to `*` and mapping `?` to `0` both
// stop throwing, which is exactly what these assertions forbid.
describe("expectedCount refuses the Quartz '?' token instead of counting zero", () => {
  const NOW = new Date("2026-10-05T23:59:00Z");
  it.each([
    ["minute", "? 9 15 * *"],
    ["hour", "30 ? 15 * *"],
    ["day of month", "30 9 ? * *"],
    ["month", "30 9 15 ? *"],
    ["day of week", "30 9 15 * ?"],
  ])("throws on ? in the %s field", (_field, cron) => {
    expect(() => expectedCount(cron, "2026-10-05", { now: NOW })).toThrow(/unsupported|\?/i);
  });

  it("throws when ? is embedded in a range rather than standing alone", () => {
    expect(() => expectedCount("0 9-? * * *", "2026-10-05", { now: NOW })).toThrow(/unsupported|\?/i);
    expect(() => expectedCount("0 ?-17 * * *", "2026-10-05", { now: NOW })).toThrow(/unsupported|\?/i);
  });

  it("throws when ? is followed by a step", () => {
    expect(() => expectedCount("*/? * * * *", "2026-10-05", { now: NOW })).toThrow(/unsupported|\?/i);
  });

  // A `?` must be refused whatever count it would have produced. These pin
  // that the answer is a refusal and not a number wearing `?`'s clothes.
  it("refuses even where every plausible interpretation agrees on the count", () => {
    // day-of-month 15 and month 10 can never be selected by any reading of `?`,
    // so "0 owed" would look right. It must still be a refusal, not a 0.
    expect(() => expectedCount("0 0 ? 10 1", "2026-10-05", { now: NOW })).toThrow(/unsupported|\?/i);
  });

  // Regression guards. The .1c guard is not to be weakened to cover `?`.
  it("still refuses a reversed range", () => {
    expect(() => expectedCount("0 0 * * FRI-MON", "2026-10-05", { now: NOW })).toThrow(/unsupported|range/i);
    expect(() => expectedCount("5-1 * * * *", "2026-10-05", { now: NOW })).toThrow(/unsupported|range/i);
  });

  it("still counts every cron that has no ? in it", () => {
    expect(expectedCount("0 0 * * *", "2026-10-05", { now: NOW })).toBe(1);
    expect(expectedCount("0 0-23/6 * * *", "2026-10-05", { now: NOW })).toBe(4);
    expect(expectedCount("*/15 * * * *", "2026-10-05", { now: NOW })).toBe(96);
    expect(expectedCount("52 * * * MON-FRI", "2026-10-05", { now: NOW })).toBe(24);
    expect(expectedCount("3 6,18 * * *", "2026-10-05", { now: NOW })).toBe(2);
  });
});
