import { describe, expect, it } from "vitest";

import { isStubPayload } from "./stub-payload";

/**
 * The fixtures below are the shapes `apps/dashboard-api/src/stubs.ts` builds.
 * The near-miss cases are the point of the leaf: each one is a plausible live
 * figure that a substring match would have called the stub.
 */

describe("stub values, matched by value", () => {
  it.each([
    ["nav as a number", 99.909],
    ["nav as a number", 204.04],
    ["since inception", 103.040192],
    ["since inception", 104.44808],
    ["since inception", 3.040191838399986],
  ])("detects %s", (_label, value) => {
    expect(isStubPayload({ data: { nav: value } })).toBe(true);
  });

  it.each([["99.909"], ["204.04"], ["204.040"]])("detects the fixture spelling %s", (value) => {
    expect(isStubPayload({ data: { nav: value } })).toBe(true);
  });

  it("finds a fixture value nested anywhere in the payload", () => {
    expect(isStubPayload({ data: { points: [{ nav: 118.75 }, { nav_tip: { nav: 99.909 } }] } })).toBe(true);
  });
});

describe("near misses are not the fixture", () => {
  it.each([
    ["one more decimal place", 99.9091],
    ["one more decimal place", 99.9092],
    ["one more decimal place", 204.041],
    ["one more decimal place", 204.045],
    ["a longer number that only contains the digits", 1204.04],
    ["a shorter neighbour", 199.909],
    ["an unrelated house NAV", 118.75],
    ["an unrelated house NAV", 101.2],
  ])("does not detect %s (%s)", (_label, value) => {
    expect(isStubPayload({ data: { nav: value } })).toBe(false);
  });

  it("does not detect a fixture value that is only a prefix of a live number", () => {
    // 99.9091 and 204.045 both contain a fixture figure's digits.
    expect(isStubPayload({ data: { nav: 99.9091, since_inception_pct: 204.045 } })).toBe(false);
  });

  it("does not detect a padded string that merely contains a fixture spelling", () => {
    expect(isStubPayload({ data: { nav: "204.045" } })).toBe(false);
    expect(isStubPayload({ data: { nav: "1204.04" } })).toBe(false);
  });
});

describe("row shapes", () => {
  const xlf = { date: "2026-09-03", ticker: "XLF", price: 54.1 };
  const gld = { date: "2026-06-01", ticker: "GLD", price: 180 };

  it("detects the stub tape only when both its closes and its date are present", () => {
    expect(
      isStubPayload({
        data: { benchmarks: [{ date: "2026-08-20", close: 500 }, { date: "2026-08-20", close: 515 }] },
      }),
    ).toBe(true);
  });

  it("does not detect one tape close without the other", () => {
    expect(isStubPayload({ data: { benchmarks: [{ date: "2026-08-20", close: 500 }] } })).toBe(false);
    expect(isStubPayload({ data: { benchmarks: [{ date: "2026-08-20", close: 515 }] } })).toBe(false);
  });

  it("does not detect the tape closes on another date", () => {
    expect(
      isStubPayload({ data: { benchmarks: [{ date: "2026-08-21", close: 500 }, { date: "2026-08-21", close: 515 }] } }),
    ).toBe(false);
  });

  it("does not detect a tape-shaped close in the low hundreds", () => {
    expect(isStubPayload({ data: { benchmarks: [{ date: "2026-08-20", close: 50 }] } })).toBe(false);
  });

  it("detects both stub ledger rows together", () => {
    expect(isStubPayload({ data: { events: [xlf, gld] } })).toBe(true);
  });

  it("detects both stub ledger rows under the other price field name", () => {
    expect(isStubPayload({ data: { events: [{ ...xlf, fill_price: 54.1 }, { ...gld, fill_price: 180 }] } })).toBe(true);
  });

  it("needs both ledger rows, not one", () => {
    expect(isStubPayload({ data: { events: [xlf] } })).toBe(false);
    expect(isStubPayload({ data: { events: [gld] } })).toBe(false);
  });

  it("needs the exact price, so a live nearby price is not the fixture", () => {
    expect(
      isStubPayload({ data: { events: [{ ...xlf, price: 54.15 }, { ...gld, price: 180.5 }] } }),
    ).toBe(false);
    expect(
      isStubPayload({ data: { events: [{ ...xlf, price: 154.1 }, { ...gld, price: 180 }] } }),
    ).toBe(false);
    expect(isStubPayload({ data: { events: [{ ...xlf, price: 54.1 }, { ...gld, price: 1180 }] } })).toBe(false);
  });

  it("needs the exact date, so a live rebalance on another day is not the fixture", () => {
    expect(
      isStubPayload({ data: { events: [{ ...xlf, date: "2026-09-04" }, { ...gld, price: 180 }] } }),
    ).toBe(false);
  });

  it("needs the exact ticker", () => {
    expect(
      isStubPayload({ data: { events: [{ ...xlf, ticker: "XLK" }, { ...gld, price: 180 }] } }),
    ).toBe(false);
  });

  it("does not combine one row's fields with another row's price", () => {
    // date + ticker from XLF, but 54.15 is not the fixture price.
    expect(
      isStubPayload({
        data: { events: [{ date: "2026-09-03", ticker: "XLF", price: 54.15 }, { ...gld, price: 180 }] },
      }),
    ).toBe(false);
  });
});

describe("a contract name is not a stub", () => {
  it("does not treat a legacy_estimate contract on its own as the fixture", () => {
    expect(isStubPayload({ data: { contract: "legacy_estimate" } })).toBe(false);
    expect(isStubPayload({ series: [{ nav: 101.2, basis: "legacy_estimate" }] })).toBe(false);
  });

  it("does not treat a house NAV series that carries both contracts as the fixture", () => {
    const house = {
      tip: { date: "2026-10-01", contract: "finalized_accounting" },
      points: [
        { date: "2026-06-01", nav: 199.909, day_return_pct: null, contract: "legacy_estimate", index: 100 },
        { date: "2026-10-01", nav: 118.75, day_return_pct: 0.4, contract: "finalized_accounting", index: 107.8 },
      ],
    };
    expect(isStubPayload(house)).toBe(false);
    // The fixture digits are present as a substring, which is the old bug.
    expect(JSON.stringify(house)).toContain("99.909");
  });
});

describe("the whole stub envelopes the surfaces ship", () => {
  it("detects the stub portfolio envelope", () => {
    expect(
      isStubPayload({
        data: {
          book_as_of: "2026-09-24",
          nav_tip: { date: "2026-09-24", nav: 99.909, contract: "legacy_estimate" },
          positions: [{ ticker: "DBO", weight_pct: 5.0031, is_cash: false }],
        },
        provenance: { contract: "legacy_estimate" },
      }),
    ).toBe(true);
  });

  it("detects the stub brief envelope", () => {
    expect(
      isStubPayload({
        data: {
          nav_tip: { date: "2026-08-28", nav: 204.04, contract: "finalized_accounting" },
          since_inception_pct: 3.040191838399986,
        },
      }),
    ).toBe(true);
  });

  it("detects a withheld upstream error as house data", () => {
    expect(
      isStubPayload({
        error: { code: "upstream_empty", message: "dashboard API has no Supabase env configured", details: {} },
      }),
    ).toBe(false);
  });
});

describe("painted display lines", () => {
  it("detects a line that paints a fixture figure", () => {
    expect(isStubPayload(["NAV 99.909", "tip 2026-09-24"])).toBe(true);
    expect(isStubPayload(["since inception 104.44808%"])).toBe(true);
  });

  it("detects a single line carrying a padded fixture spelling", () => {
    expect(isStubPayload(["nav 204.040"])).toBe(true);
  });

  it("does not detect lines that only contain the digits", () => {
    expect(isStubPayload(["NAV 199.909", "since inception 204.045%"])).toBe(false);
    expect(isStubPayload(["NAV 1204.04", "GLD 1180"])).toBe(false);
  });

  it("does not detect the stub banner sentence itself", () => {
    expect(isStubPayload(["===[STUB_READ] stub envelope, not a house-book read"])).toBe(false);
  });

  it("accepts a bare string", () => {
    expect(isStubPayload("NAV 99.909")).toBe(true);
    expect(isStubPayload("NAV 199.909")).toBe(false);
  });

  it("does not apply the row conjunctions to painted lines", () => {
    // Both figures are there but on different lines with ordinary rows around
    // them. A painted line carries bare numbers, so this is not evidence.
    expect(
      isStubPayload([
        "XLF 2026-09-03  trim  9.90% -> 4.90%",
        "GLD 2026-06-01  open  0.00% -> 10.00%",
      ]),
    ).toBe(false);
  });
});

describe("shapes the detector must survive", () => {
  it("does not recurse forever on a self-referencing payload", () => {
    const cyclic: Record<string, unknown> = { data: {} };
    (cyclic.data as Record<string, unknown>).self = cyclic;
    expect(isStubPayload(cyclic)).toBe(false);
  });

  it("reads a number painted with a negative sign as its own value", () => {
    expect(isStubPayload({ data: { day_return_pct: -54.15 } })).toBe(false);
  });

  it("reads null and primitives as house data", () => {
    expect(isStubPayload(null)).toBe(false);
    expect(isStubPayload(undefined)).toBe(false);
    expect(isStubPayload(0)).toBe(false);
    expect(isStubPayload("")).toBe(false);
  });

  it("tolerates a string-typed ledger price", () => {
    expect(
      isStubPayload({
        data: {
          events: [
            { date: "2026-09-03", ticker: "XLF", price: "54.1" },
            { date: "2026-06-01", ticker: "GLD", price: "180" },
          ],
        },
      }),
    ).toBe(true);
  });
});