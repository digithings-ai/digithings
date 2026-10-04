import { describe, expect, it } from "vitest";
import {
  maxThesisDate,
  rowsAtDate,
  thesisShape,
  THESIS_STATUSES,
  type ThesisCounts,
} from "./thesis-shape";

/**
 * Unit coverage for the parts of the mapper the route tests cannot reach: the
 * jsonb criteria columns, which arrive from PostgREST as whatever the writer
 * put in them.
 */

function countsTotal(counts: ThesisCounts): number {
  return Object.values(counts.by_status).reduce((a, b) => a + b, 0);
}

describe("criteria rendering", () => {
  it("reads text out of a jsonb array of objects", () => {
    const { theses } = thesisShape([
      {
        thesis_id: "a",
        name: "A",
        status: "ACTIVE",
        validation_criteria: [{ condition: "yields below 2%" }, { text: "DXY under 100" }],
        invalidation_criteria: [{ statement: "yields above 3%" }],
      },
    ], []);
    expect(theses[0].evidence).toBe("yields below 2%; DXY under 100");
    expect(theses[0].kill_condition).toBe("yields above 3%");
  });

  it("accepts bare strings, numbers and a JSON-encoded jsonb column", () => {
    const { theses } = thesisShape([
      { thesis_id: "a", name: "A", status: "ACTIVE", validation_criteria: ["spot holds", 3] },
      { thesis_id: "b", name: "B", status: "ACTIVE", invalidation_criteria: '[{"condition":"oil > $140"}]' },
    ], []);
    expect(theses[0].evidence).toBe("spot holds; 3");
    expect(theses[1].kill_condition).toBe("oil > $140");
  });

  it("drops an element with no recognisable text and repeats nothing", () => {
    const { theses } = thesisShape([
      {
        thesis_id: "a",
        name: "A",
        status: "ACTIVE",
        validation_criteria: [{ condition: "spot holds" }, { "condition": "spot holds" }, { metric: 7 }, null],
      },
    ], []);
    expect(theses[0].evidence).toBe("spot holds");
  });

  // A criterion can be a bare threshold or a flag rather than a sentence, and a
  // string-only read turned `{ condition: 2 }` into an empty evidence cell — the
  // same silent-hole failure the three removed columns had.
  it("reads a numeric or boolean criterion value as its own text", () => {
    const { theses } = thesisShape([
      { thesis_id: "a", name: "A", status: "ACTIVE", validation_criteria: [{ value: 105 }, { condition: true }] },
      { thesis_id: "b", name: "B", status: "ACTIVE", invalidation_criteria: [{ condition: 2 }] },
      { thesis_id: "c", name: "C", status: "ACTIVE", validation_criteria: [{ condition: Number.NaN }] },
    ], []);
    expect(theses[0].evidence).toBe("105; true");
    expect(theses[1].kill_condition).toBe("2");
    expect(theses[2].evidence).toBeNull();
  });

  // The jsonb columns have no maxItems and both consumers render this into one
  // table cell, so an unbounded join is a layout hazard.
  it("caps the rendered cell and marks it as truncated", () => {
    const many = Array.from({ length: 40 }, (_, i) => ({ condition: `criterion number ${i} holds` }));
    const { theses } = thesisShape([{ thesis_id: "a", name: "A", status: "ACTIVE", validation_criteria: many }], []);
    const evidence = theses[0].evidence ?? "";
    expect(evidence.endsWith("…")).toBe(true);
    expect(evidence.length).toBeLessThanOrEqual(400);
    expect(evidence).toContain("criterion number 0 holds");
    expect(evidence).not.toContain("criterion number 39 holds");
  });

  // The only path that can put JSON punctuation in front of a reader is a
  // `[`-prefixed string that does not parse. It is shown as the text it is.
  it("shows a malformed JSON-looking string verbatim rather than dropping it", () => {
    const { theses } = thesisShape([
      { thesis_id: "a", name: "A", status: "ACTIVE", validation_criteria: "[see note 3" },
    ], []);
    expect(theses[0].evidence).toBe("[see note 3");
  });

  // A jsonb column need not be an array; a bare object is read the same way.
  it("reads a single top-level object without an array wrapper", () => {
    const { theses } = thesisShape([
      { thesis_id: "a", name: "A", status: "ACTIVE", validation_criteria: { condition: "spot holds" } },
    ], []);
    expect(theses[0].evidence).toBe("spot holds");
  });

  it("falls back to the free-text invalidation when the jsonb column is empty", () => {
    const { theses } = thesisShape([
      { thesis_id: "a", name: "A", status: "ACTIVE", invalidation_criteria: [], invalidation: "Fed re-tightens" },
      { thesis_id: "b", name: "B", status: "ACTIVE", invalidation_criteria: [{ condition: "jsonb wins" }], invalidation: "text loses" },
    ], []);
    expect(theses[0].kill_condition).toBe("Fed re-tightens");
    expect(theses[1].kill_condition).toBe("jsonb wins");
  });

  // The defect DIG-486 was raised for: these three were read off the row, and no
  // core `theses` column carries them, so a value under any of the three names
  // can only have come from a pre-shaped fixture — it must not reach the pane.
  it("does not read the three fields that are not theses columns", () => {
    const { theses } = thesisShape([
      {
        thesis_id: "a", name: "A", status: "ACTIVE",
        evidence: "invented", kill_condition: "invented", note: "invented",
      },
    ], []);
    expect(theses[0].evidence).toBeNull();
    expect(theses[0].kill_condition).toBeNull();
    expect(theses[0].note).toBeNull();
  });

  it("reads the columns that do exist", () => {
    const { theses } = thesisShape([
      {
        thesis_id: "a", name: "A", status: "ACTIVE",
        notes: "  Trimmed on Friday.  ", invalidation: "  Stops working if spreads widen.  ",
      },
    ], []);
    expect(theses[0].note).toBe("Trimmed on Friday.");
    expect(theses[0].kill_condition).toBe("Stops working if spreads widen.");
  });
});

describe("counts", () => {
  it("covers every token chk_theses_status allows and none of them go missing", () => {
    const { theses, counts } = thesisShape(
      THESIS_STATUSES.map((status) => ({ thesis_id: status, name: status, status: status.toUpperCase() })),
      [],
    );
    expect(theses).toHaveLength(THESIS_STATUSES.length);
    expect(counts.by_status.unknown).toBe(0);
    for (const status of THESIS_STATUSES) expect(counts.by_status[status]).toBe(1);
    expect(counts.active).toBe(1);
    expect(counts.watch).toBe(2);
    expect(counts.exited).toBe(2);
    // The headline buckets plus the two tokens they do not cover account for
    // every row, so a count can never be quietly wrong.
    expect(counts.active + counts.watch + counts.exited + counts.by_status.paused + counts.by_status.new).toBe(
      theses.length,
    );
  });

  // A NULL `status` is the case the table can actually produce — the constraint
  // permits NULL. Whitespace cannot be written, so that row is defensive only.
  it("buckets a NULL status as unknown rather than as any live token", () => {
    const { counts } = thesisShape(
      [
        { thesis_id: "a", name: "A", status: null },
        { thesis_id: "b", name: "B" },
        { thesis_id: "c", name: "C", status: "  " },
      ],
      [],
    );
    expect(counts.by_status.unknown).toBe(3);
    expect(countsTotal(counts)).toBe(3);
  });

  it("is all zeros for an empty book", () => {
    const { theses, counts } = thesisShape([], []);
    expect(theses).toEqual([]);
    expect(countsTotal(counts)).toBe(0);
    expect(counts).toEqual({
      active: 0, watch: 0, exited: 0,
      by_status: {
        active: 0, monitoring: 0, challenged: 0, closed: 0,
        invalidated: 0, paused: 0, new: 0, unknown: 0,
      },
    });
  });
});

describe("vehicles", () => {
  it("joins on thesis_id and never on the uuid id", () => {
    const { theses } = thesisShape(
      [{ id: "fd49f84b-114b-4e73-ab87-f16939664f97", thesis_id: "gold-bid", name: "Gold", status: "ACTIVE" }],
      [
        { thesis_id: "gold-bid", ticker: "GLD" },
        { thesis_id: "gold-bid", ticker: "IAU" },
        { thesis_id: "fd49f84b-114b-4e73-ab87-f16939664f97", ticker: "WRONG" },
      ],
    );
    expect(theses[0].vehicles).toEqual(["GLD", "IAU"]);
  });

  // `(date, thesis_id, ticker)` is the primary key so the FK cannot orphan a
  // vehicle row; the mapper is exported and both routes hand it a merged read,
  // so an unmatched row must be dropped rather than pooled into some thesis.
  it("drops a vehicle row that matches no thesis at the pinned date", () => {
    const { theses } = thesisShape(
      [{ thesis_id: "gold-bid", name: "Gold", status: "ACTIVE" }],
      [
        { thesis_id: "gold-bid", ticker: "GLD" },
        { thesis_id: "silver-bid", ticker: "SLV" },
        { thesis_id: "gold-bid" },
        { ticker: "IAU" },
      ],
    );
    expect(theses[0].vehicles).toEqual(["GLD"]);
  });

  it("lists a repeated ticker once", () => {
    const { theses } = thesisShape(
      [{ thesis_id: "gold-bid", name: "Gold", status: "ACTIVE" }],
      [{ thesis_id: "gold-bid", ticker: "GLD" }, { thesis_id: "gold-bid", ticker: "GLD" }],
    );
    expect(theses[0].vehicles).toEqual(["GLD"]);
  });
});

describe("business date", () => {
  it("takes the tip from date and ignores updated_at", () => {
    const rows = [
      { thesis_id: "a", date: "2026-09-20", updated_at: "2026-10-09T00:00:00Z" },
      { thesis_id: "a", date: "2026-09-28", updated_at: "2026-09-28T00:00:00Z" },
      { thesis_id: "b", updated_at: "2026-10-09T00:00:00Z" },
    ];
    const tip = maxThesisDate(rows);
    expect(tip).toBe("2026-09-28");
    expect(rowsAtDate(rows, tip).map((r) => r.thesis_id)).toEqual(["a"]);
  });

  it("keeps nothing when no row carries a date", () => {
    expect(maxThesisDate([{ thesis_id: "a" }])).toBeNull();
    expect(rowsAtDate([{ thesis_id: "a" }], null)).toEqual([]);
  });
});
