import { describe, expect, it } from "vitest";
import { expectedCount } from "./expected";

describe("expectedCount", () => {
  it("A.7 an hourly weekday clock owes 24 starts on a Monday", () => {
    expect(expectedCount("52 * * * MON-FRI", "2026-09-28")).toBe(24);
  });
  it("A.7 the same clock owes nothing on a Sunday", () => {
    expect(expectedCount("52 * * * MON-FRI", "2026-09-29")).toBe(0);
  });
  it("counts hour lists and step syntax", () => {
    expect(expectedCount("3 6,18 * * *", "2026-10-05")).toBe(2);
    expect(expectedCount("4 */4 * * *", "2026-10-05")).toBe(6);
  });
  it("counts a day-of-month rule", () => {
    expect(expectedCount("0 0 15 * *", "2026-10-15")).toBe(1);
    expect(expectedCount("0 0 15 * *", "2026-10-16")).toBe(0);
  });
  it("counts only the minutes already due on the day in progress", () => {
    expect(
      expectedCount("52 * * * MON-FRI", "2026-10-05", { now: new Date("2026-10-05T10:00:00Z") }),
    ).toBe(10);
  });
});