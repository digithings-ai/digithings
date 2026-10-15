import { expect, test } from "bun:test";
import { DASH, asOfStatus, cell, fieldKind, formatTimestamp, toneOf } from "./format";
import { fieldLines, presentResponse } from "./read";

test("a raw float is rounded by its field, never painted as sent", () => {
  expect(cell(123.50887821352958, "nav")).toBe("123.51");
  expect(cell(123.50887821352958)).toBe("123.51");
  expect(cell(0.123456789)).toBe("0.1235");
  expect(cell(1234567.891, "current_price")).toBe("1,234,567.89");
  expect(cell(1.0842391, "bid")).toBe("1.0842");
  expect(cell(0.80123, "beta")).toBe("0.80");
  expect(cell(12000, "tokens_in")).toBe("12,000");
  expect(cell(2026)).toBe("2026");
});

test("returns carry a sign; weights and shares of the book do not", () => {
  expect(cell(0.4, "day_return_pct")).toBe("+0.40%");
  expect(cell(-1.234, "since_inception_pct")).toBe("-1.23%");
  expect(cell(12.5, "weight_pct")).toBe("12.50%");
  expect(cell(80, "invested_pct")).toBe("80.00%");
  expect(cell(12.5, "contribution_bp")).toBe("+12.5");
  expect(fieldKind("excess_live_pct")).toBe("signed-pct");
  expect(fieldKind("scaled_weight_pct")).toBe("pct");
});

test("null is a dash and zero is a number", () => {
  expect(cell(null, "day_return_pct")).toBe(DASH);
  expect(cell(undefined, "nav")).toBe(DASH);
  expect(cell("", "nav")).toBe(DASH);
  expect(cell(Number.NaN, "nav")).toBe(DASH);
  expect(cell(0, "day_return_pct")).toBe("0.00%");
  expect(cell(0, "nav")).toBe("0.00");
  expect(cell(-0.001, "day_return_pct")).toBe("0.00%");
});

test("currency fields name the dollar and keep cents of a cent under one dollar", () => {
  expect(cell(1234.5, "cost_usd")).toBe("$1,234.50");
  expect(cell(0.00421, "cost_usd")).toBe("$0.0042");
  expect(cell(-20, "pnl_usd")).toBe("-$20.00");
});

test("a numeric string under a numeric key is formatted; other strings stay verbatim", () => {
  expect(cell("12.5", "weight_pct")).toBe("12.50%");
  expect(cell("AAA", "ticker")).toBe("AAA");
  expect(cell("12.5", "note")).toBe("12.5");
});

test("a calendar date is never shifted; a timestamp names its zone", () => {
  expect(cell("2026-10-09", "date")).toBe("2026-10-09");
  expect(formatTimestamp("2026-10-10T12:05:00Z", "UTC")).toBe("2026-10-10 12:05 UTC");
  expect(formatTimestamp("2026-10-10T12:05:00Z", "Europe/Rome")).toBe("2026-10-10 14:05 GMT+2");
  expect(formatTimestamp("2026-10-10T23:30:00Z", "America/New_York")).toBe("2026-10-10 19:30 EDT");
});

test("tone is read off the signed text, and a zero or an unsigned figure has none", () => {
  expect(toneOf("+0.40%")).toBe("up");
  expect(toneOf("-1.23%")).toBe("down");
  expect(toneOf("-$20.00")).toBe("down");
  expect(toneOf("0.00%")).toBeNull();
  expect(toneOf("12.50%")).toBeNull();
  expect(toneOf(DASH)).toBeNull();
  expect(toneOf("-")).toBeNull();
});

test("the footer shows both dates when they differ and ages the data date", () => {
  expect(asOfStatus("/brief", null, null, "2026-10-09")).toEqual({ label: "/brief", age: null, state: null });
  expect(asOfStatus("/brief", null, "2026-10-09", "2026-10-09")).toEqual({
    label: "as of 2026-10-09 · current session",
    age: "current session",
    state: "fresh",
  });
  expect(asOfStatus("/brief", "2026-10-09", "2026-10-06", "2026-10-09").label).toBe(
    "as of 2026-10-09 · data 2026-10-06 · 3 trading days old · stale",
  );
  expect(asOfStatus("/brief", null, "2026-10-07", "2026-10-09").state).toBe("warn");
  // One trading day is fresh at the default threshold and stale when the caller sets it to 1.
  expect(asOfStatus("/brief", null, "2026-10-08", "2026-10-09").state).toBe("fresh");
  expect(asOfStatus("/brief", null, "2026-10-08", "2026-10-09", 1).state).toBe("stale");
  // Friday's data read on Sunday has not missed a session.
  expect(asOfStatus("/brief", null, "2026-10-09", "2026-10-11").age).toBe("current session");
  // Ahead of the clock is skew, not freshness.
  expect(asOfStatus("/brief", null, "2026-10-12", "2026-10-09")).toEqual({ label: "as of 2026-10-12", age: null, state: null });
});

test("presentResponse formats fields and carries the data date beside the asked date", () => {
  const read = presentResponse(
    "/brief",
    200,
    {
      data: { book_as_of: "2026-10-08", nav: 123.50887821352958, day_return_pct: -0.4123, cash_pct: 0 },
      as_of: null,
      provenance: { source: "core:nav", tip_date: "2026-10-08" },
    },
    "fields",
  );
  expect(read.lines).toEqual([
    "source  core:nav",
    "book_as_of  2026-10-08",
    "nav  123.51",
    "day_return_pct  -0.41%",
    "cash_pct  0.00%",
  ]);
  expect(read.asOf).toBeNull();
  expect(read.dataAsOf).toBe("2026-10-08");
  expect(fieldLines({ rows: [{ ticker: "AAA", day_return_pct: 1 }] })).toEqual(["rows  1. ticker AAA  day_return_pct +1.00%"]);
});
