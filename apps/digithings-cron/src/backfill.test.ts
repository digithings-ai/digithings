import { describe, expect, it } from "vitest";
import {
  BACKFILL_INPUT_KEYS,
  MAX_BACKFILL_DATES,
  buildPlan,
  isIsoDate,
  splitDateList,
} from "./backfill";

/** Narrow a refusal to its code so tests read as the ladder, not the shape. */
function refuse(body: unknown): { code: string; detail: string } {
  const plan = buildPlan(typeof body === "string" ? body : JSON.stringify(body));
  if (plan.ok) throw new Error(`expected a refusal, got ${JSON.stringify(plan)}`);
  return { code: plan.code, detail: plan.detail };
}

function accept(body: unknown): { dates: string[]; force_dates: boolean } {
  const plan = buildPlan(JSON.stringify(body));
  if (!plan.ok) throw new Error(`expected a plan, got ${plan.code}: ${plan.detail}`);
  return { dates: plan.dates, force_dates: plan.force_dates };
}

describe("isIsoDate", () => {
  it("accepts real calendar dates", () => {
    expect(isIsoDate("2026-06-02")).toBe(true);
    expect(isIsoDate("2026-02-28")).toBe(true);
    expect(isIsoDate("2024-02-29")).toBe(true);
  });

  it("rejects a day that does not exist", () => {
    // The normalisation trap: these parse as strings but name no real day.
    expect(isIsoDate("2026-02-30")).toBe(false);
    expect(isIsoDate("2026-13-01")).toBe(false);
    expect(isIsoDate("2026-00-10")).toBe(false);
    expect(isIsoDate("2026-06-00")).toBe(false);
    expect(isIsoDate("2025-02-29")).toBe(false);
  });

  it("rejects anything that is not exactly YYYY-MM-DD", () => {
    expect(isIsoDate("2026-6-2")).toBe(false);
    expect(isIsoDate("06-02-2026")).toBe(false);
    expect(isIsoDate("2026/06/02")).toBe(false);
    expect(isIsoDate("2026-06-02T00:00:00Z")).toBe(false);
    expect(isIsoDate("")).toBe(false);
  });
});

describe("splitDateList", () => {
  it("trims parts and drops empties", () => {
    expect(splitDateList(" 2026-06-02 , 2026-06-03 ,, ")).toEqual([
      "2026-06-02",
      "2026-06-03",
    ]);
  });

  it("accepts a newline-separated remediation list", () => {
    expect(splitDateList("2026-06-02\n2026-06-03\n2026-06-04")).toEqual([
      "2026-06-02",
      "2026-06-03",
      "2026-06-04",
    ]);
  });

  it("accepts mixed commas, newlines and spaces", () => {
    expect(splitDateList("2026-06-02, 2026-06-03\n  2026-06-04\n\n2026-06-05")).toEqual([
      "2026-06-02",
      "2026-06-03",
      "2026-06-04",
      "2026-06-05",
    ]);
  });

  it("never splits a valid date in half", () => {
    // A YYYY-MM-DD token has no whitespace, so whitespace as a separator is safe.
    expect(splitDateList("2026-06-02")).toEqual(["2026-06-02"]);
    expect(splitDateList("2024-02-29")).toEqual(["2024-02-29"]);
  });
});

describe("buildPlan", () => {
  it("returns the dates a caller named", () => {
    expect(accept({ dates: "2026-06-02,2026-06-03" })).toEqual({
      dates: ["2026-06-02", "2026-06-03"],
      force_dates: false,
    });
  });

  it("accepts a newline-separated list end to end", () => {
    // The remediation list this endpoint exists for arrives pasted out of an
    // incident record, so newlines are a first-class separator, not an accident.
    expect(accept({ dates: "2026-06-02\n2026-06-03" }).dates).toEqual([
      "2026-06-02",
      "2026-06-03",
    ]);
  });

  it("sorts and collapses duplicates so a repeat date is one unit of work", () => {
    expect(accept({ dates: "2026-06-03,2026-06-02,2026-06-03" }).dates).toEqual([
      "2026-06-02",
      "2026-06-03",
    ]);
  });

  it("counts force_dates only when it is the string true", () => {
    expect(accept({ dates: "2026-06-02", force_dates: "true" }).force_dates).toBe(true);
    expect(accept({ dates: "2026-06-02" }).force_dates).toBe(false);
  });

  it("refuses a body that is not JSON", () => {
    expect(refuse("{not json").code).toBe("invalid_json");
  });

  it("refuses a body that is not an object", () => {
    expect(refuse("[]").code).toBe("invalid_args");
    expect(refuse('"2026-06-02"').code).toBe("invalid_args");
    expect(refuse("null").code).toBe("invalid_args");
  });

  it("refuses a non-string value", () => {
    expect(refuse({ dates: ["2026-06-02"] }).code).toBe("invalid_args");
    expect(refuse({ dates: 20260602 }).code).toBe("invalid_args");
  });

  it("refuses run_date, the key that caused the 2026-09-28 outage shape", () => {
    // run_date belongs to daily_run.yml. maintenance.yml has no such input, so
    // GitHub answers 422 while the caller logs success and starts zero runs.
    const refusal = refuse({ dates: "2026-06-02", run_date: "2026-06-02" });
    expect(refusal.code).toBe("unexpected_arg");
    expect(refusal.detail).toContain("run_date");
  });

  it("refuses since and until even though upstream supports them", () => {
    // A range cannot be made idempotent per date from this Worker, so the
    // sanctioned surface takes named dates only.
    expect(refuse({ dates: "2026-06-02", since: "2026-06-02" }).code).toBe(
      "unexpected_arg",
    );
    expect(refuse({ until: "2026-06-02" }).code).toBe("unexpected_arg");
    expect(refuse({ since: "2026-06-02", until: "2026-06-09" }).detail).toContain("since");
  });

  it("refuses an unexpected key even when its value is well-formed", () => {
    expect(refuse({ dates: "2026-06-02", backfill_snapshots: "true" }).code).toBe(
      "unexpected_arg",
    );
  });

  it("refuses a force_dates that is not the string true", () => {
    expect(refuse({ dates: "2026-06-02", force_dates: "yes" }).code).toBe("invalid_args");
    expect(refuse({ dates: "2026-06-02", force_dates: "false" }).code).toBe("invalid_args");
  });

  it("refuses a bare kick", () => {
    // The guard the CEO named: a dispatch carrying no date selector never
    // reaches the ledger, let alone upstream.
    expect(refuse({}).code).toBe("missing_required_arg");
    expect(refuse({ force_dates: "true" }).code).toBe("missing_required_arg");
  });

  it("refuses blank and separator-only dates", () => {
    expect(refuse({ dates: "" }).code).toBe("missing_required_arg");
    expect(refuse({ dates: "   " }).code).toBe("missing_required_arg");
    expect(refuse({ dates: ",,," }).code).toBe("invalid_dates");
  });

  it("names the offending element when a date is not real", () => {
    const refusal = refuse({ dates: "2026-06-02,2026-02-30" });
    expect(refusal.code).toBe("invalid_dates");
    expect(refusal.detail).toContain("2026-02-30");
  });

  it("refuses more distinct dates than the cap, after collapsing duplicates", () => {
    // Spread over two real months so n distinct dates really are n distinct.
    const many = (n: number) =>
      Array.from({ length: n }, (_, i) =>
        i < 30
          ? `2026-06-${String(i + 1).padStart(2, "0")}`
          : `2026-07-${String(i - 29).padStart(2, "0")}`,
      ).join(",");
    expect(accept({ dates: many(MAX_BACKFILL_DATES) }).dates.length).toBe(
      MAX_BACKFILL_DATES,
    );
    expect(refuse({ dates: many(MAX_BACKFILL_DATES + 1) }).code).toBe("too_many_dates");
    // 90 sent, 3 distinct: still 3 units of work, so the cap must not trip on
    // raw element count.
    const tripled = "2026-06-01,2026-06-01,2026-06-01,2026-06-02,2026-06-02,2026-06-02,";
    expect(accept({ dates: tripled.repeat(15) }).dates).toEqual([
      "2026-06-01",
      "2026-06-02",
    ]);
  });
});

describe("allowlist", () => {
  it("is exactly dates and force_dates", () => {
    expect([...BACKFILL_INPUT_KEYS]).toEqual(["dates", "force_dates"]);
  });
});
