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
      expectedCount("52 * * * MON-FRI", "2026-10-05", { now: new Date("2026-10-05T10:00:00Z") }),
    ).toBe(10);
  });
});