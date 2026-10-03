import { expect, test } from "bun:test";
import { EMPTY_READ, STUB_READ, type ReadResult } from "../read";
import { ledgerBody } from "./ledger-format";

const ok = (lines: string[] = []): ReadResult => ({ status: "ok", lines, asOf: "2026-02-01" });

test("a stub, a missed API, and an empty read stay the exact sentence", () => {
  const missed = "/ledger?limit=50: the official API could not be reached.";
  expect(ledgerBody("ledger", null, { status: "error", lines: [missed], asOf: null })).toEqual({
    blocks: [{ kind: "sentence", text: missed }],
  });
  expect(
    ledgerBody(
      "ledger",
      {
        events: [{ date: "2026-09-03", ticker: "XLF", type: "TRIM", fill_price: 54.1 }],
      },
      { status: "stub", lines: [STUB_READ], asOf: null },
    ),
  ).toEqual({
    blocks: [{ kind: "sentence", text: STUB_READ }],
  });
  expect(ledgerBody("cash", null, { status: "empty", lines: [EMPTY_READ], asOf: null })).toEqual({
    blocks: [{ kind: "sentence", text: EMPTY_READ }],
  });
  const cashMissed = "/ledger/cash: the official API could not be reached.";
  expect(ledgerBody("cash", { entries: [{ date: "2026-02-01", kind: "period", amount: 1 }] }, { status: "error", lines: [cashMissed], asOf: null })).toEqual({
    blocks: [{ kind: "sentence", text: cashMissed }],
  });
});

test("position events are a table, and a missing fill stays blank", () => {
  const body = ledgerBody(
    "ledger",
    {
      events: [
        {
          date: "2026-02-01",
          ticker: "AAA",
          type: "TRIM",
          fill_price: 12.5,
          avg_entry: 10,
          realized_pct: 25,
          prev_weight_pct: 8,
          weight_pct: 4,
        },
        {
          date: "2026-01-15",
          ticker: "BBB",
          type: "OPEN",
          fill_price: null,
          avg_entry: null,
          realized_pct: null,
          prev_weight_pct: null,
          weight_pct: 3,
        },
      ],
      next_cursor: "cursor-token",
    },
    ok(["source  position_events+positions"]),
  );
  expect(body.blocks).toEqual([
    { kind: "stat", text: "source  position_events+positions" },
    {
      kind: "table",
      columns: ["date", "ticker", "type", "fill", "entry", "realized", "prev", "weight"],
      rows: [
        ["2026-02-01", "AAA", "TRIM", "12.5", "10", "25", "8", "4"],
        ["2026-01-15", "BBB", "OPEN", "—", "—", "—", "—", "3"],
      ],
    },
  ]);
  const text = JSON.stringify(body);
  expect(text).not.toContain("cursor-token");
  expect(text).not.toContain("→");
  expect(text).not.toContain("%");
});

test("cash is its own table, and a missing amount is not replaced", () => {
  const body = ledgerBody(
    "cash",
    {
      entries: [
        { date: "2026-02-01", kind: "period", amount: -20, balance: 80 },
        { date: "2026-01-01", kind: null, amount: null, balance: null },
      ],
      total: 100,
    },
    ok(["source  core:accounting_periods+position_events"]),
  );
  expect(body.blocks).toEqual([
    { kind: "stat", text: "source  core:accounting_periods+position_events" },
    {
      kind: "table",
      columns: ["date", "kind", "amount", "balance"],
      rows: [
        ["2026-02-01", "period", "-20", "80"],
        ["2026-01-01", "—", "—", "—"],
      ],
    },
  ]);
  expect(JSON.stringify(body)).not.toContain("100");
});

test("an empty list stays the empty sentence and does not invent a row", () => {
  expect(ledgerBody("ledger", { events: [], next_cursor: "more" }, ok())).toEqual({
    blocks: [{ kind: "sentence", text: EMPTY_READ }],
  });
  expect(ledgerBody("cash", { entries: [], total: 40 }, ok())).toEqual({
    blocks: [{ kind: "sentence", text: EMPTY_READ }],
  });
  expect(ledgerBody("ledger", { events: [{ type: "OPEN", fill_price: 9 }] }, ok())).toEqual({
    blocks: [{ kind: "sentence", text: EMPTY_READ }],
  });
  const text = JSON.stringify(ledgerBody("cash", { entries: [], total: 40 }, ok()));
  expect(text).not.toContain("40");
  expect(text).not.toContain("9");
});
