import { expect, test } from "bun:test";
import { EMPTY_READ, STUB_READ, type ReadResult } from "../read";
import { holdingsBody } from "./holdings-format";

const ok = (lines: string[] = []): ReadResult => ({ status: "ok", lines, asOf: "2026-01-02" });

test("a stub, a missed API, and an empty read stay the exact sentence", () => {
  const missed = "/allocations/enriched: the official API could not be reached.";
  expect(holdingsBody("holdings", null, { status: "error", lines: [missed], asOf: null })).toEqual({
    blocks: [{ kind: "sentence", text: missed }],
  });
  expect(holdingsBody("holdings", { rows: [{ ticker: "AAA" }] }, { status: "stub", lines: [STUB_READ], asOf: null })).toEqual({
    blocks: [{ kind: "sentence", text: STUB_READ }],
  });
  expect(holdingsBody("holdings", null, { status: "empty", lines: [EMPTY_READ], asOf: null })).toEqual({
    blocks: [{ kind: "sentence", text: EMPTY_READ }],
  });
});

test("holdings is the enriched book rows, with a missing price left blank", () => {
  const body = holdingsBody(
    "holdings",
    {
      book_as_of: "2026-01-02",
      sleeves: [{ sleeve: "Core", names: 1, weight_pct: 10 }],
      cash_value: 40,
      book_value: 100,
      rows: [
        {
          ticker: "AAA",
          name: "Alpha",
          sleeve: "Core",
          scaled_weight_pct: 10,
          shares: 4,
          current_price: null,
          value: null,
          day_return_pct: 1.5,
          thesis_id: "th-1",
          is_cash: false,
        },
        { ticker: "CASH", name: null, sleeve: null, scaled_weight_pct: null, shares: null, current_price: null, is_cash: true },
      ],
    },
    ok(["source  core:positions+instruments"]),
  );
  expect(body.blocks).toEqual([
    { kind: "stat", text: "source  core:positions+instruments" },
    {
      kind: "table",
      columns: ["ticker", "name", "sleeve", "weight", "shares", "price", "value", "day", "thesis"],
      rows: [
        ["AAA", "Alpha", "Core", "10", "4", "—", "—", "1.5", "th-1"],
        ["CASH", "—", "—", "—", "—", "—", "—", "—", "—"],
      ],
    },
  ]);
  const text = JSON.stringify(body);
  expect(text).not.toContain("40");
  expect(text).not.toContain("100");
  expect(text).not.toContain("Book total");
});

test("an empty book stays the empty sentence and does not invent a sleeve row", () => {
  expect(holdingsBody("holdings", { rows: [], sleeves: [{ sleeve: "Core", names: 2, weight_pct: 40 }] }, ok())).toEqual({
    blocks: [{ kind: "sentence", text: EMPTY_READ }],
  });
  expect(holdingsBody("holdings", { rows: [{ name: "no ticker" }] }, ok())).toEqual({
    blocks: [{ kind: "sentence", text: EMPTY_READ }],
  });
});
