import { describe, expect, it } from "vitest";
import { isIsoDate } from "./routes";

describe("isIsoDate", () => {
  it("accepts a calendar date", () => {
    expect(isIsoDate("2026-10-20")).toBe(true);
    expect(isIsoDate("2024-02-29")).toBe(true);
  });

  it("rejects a day the calendar does not have", () => {
    expect(isIsoDate("2023-02-29")).toBe(false);
    expect(isIsoDate("2026-02-30")).toBe(false);
    expect(isIsoDate("2026-13-01")).toBe(false);
  });

  it("rejects anything that is not a plain date", () => {
    expect(isIsoDate("2026-10-20T00:00:00Z")).toBe(false);
    expect(isIsoDate("20261020")).toBe(false);
    expect(isIsoDate("20-10-2026")).toBe(false);
    expect(isIsoDate("")).toBe(false);
  });

  it("rejects a year the container cannot parse", () => {
    // The container parses the value with Python's date.fromisoformat, which
    // has no year 0.
    expect(isIsoDate("0000-01-01")).toBe(false);
    expect(isIsoDate("0000-02-29")).toBe(false);
    expect(isIsoDate("0001-01-01")).toBe(true);
  });
});
