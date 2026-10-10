import { expect, test } from "bun:test";
import { EMPTY_READ, STUB_READ, type ReadResult } from "../read";
import { portfolioBody } from "./portfolio-format";

const ok = (lines: string[] = []): ReadResult => ({ status: "ok", lines, asOf: "2026-01-02" });

test("a stub, a missed API, and an empty read stay the exact sentence", () => {
  const missed = "/portfolio: the official API could not be reached.";
  expect(portfolioBody("portfolio", null, { status: "error", lines: [missed], asOf: null })).toEqual({
    blocks: [{ kind: "sentence", text: missed }],
  });
  expect(portfolioBody("portfolio", { nav_tip: { nav: 1 } }, { status: "stub", lines: [STUB_READ], asOf: null })).toEqual({
    blocks: [{ kind: "sentence", text: STUB_READ }],
  });
  expect(portfolioBody("nav", null, { status: "empty", lines: [EMPTY_READ], asOf: null })).toEqual({
    blocks: [{ kind: "sentence", text: EMPTY_READ }],
  });
});

test("the envelope is a stat of the NAV tip, invested, and cash", () => {
  const body = portfolioBody(
    "portfolio",
    {
      nav_tip: { date: "2026-01-02", nav: 101.2, contract: "finalized_accounting", invested_pct: 80, cash_pct: 20 },
      invested: { kpi_pct: 135, envelope_pct: 80, cash_pct: 20, definition: "accounting_nav_tip" },
    },
    ok(["source  public_accounting_nav_history"]),
  );
  expect(body.blocks).toEqual([
    { kind: "stat", text: "source  public_accounting_nav_history" },
    {
      kind: "stat",
      text: "NAV  101.2   date  2026-01-02   contract  finalized_accounting   invested  80   cash  20",
    },
  ]);
  expect(JSON.stringify(body)).not.toContain("135");
  expect(
    portfolioBody(
      "portfolio",
      { nav_tip: { nav: 10 }, invested: { envelope_pct: 80, cash_pct: null } },
      ok(),
    ).blocks,
  ).toEqual([{ kind: "stat", text: "NAV  10   invested  80" }]);
  expect(
    portfolioBody("portfolio", { nav_tip: null, invested: { envelope_pct: null, cash_pct: null } }, ok()),
  ).toEqual({ blocks: [{ kind: "sentence", text: EMPTY_READ }] });
});

test("sleeves, movers, and the book are tables, or the empty sentence", () => {
  expect(
    portfolioBody("sleeves", { sleeves: [{ sleeve: "Core", names: 2, weight_pct: 40 }], rows: [{ ticker: "AAA" }] }, ok())
      .blocks,
  ).toEqual([{ kind: "table", columns: ["sleeve", "names", "weight"], rows: [["Core", "2", "40"]] }]);
  expect(portfolioBody("sleeves", { sleeves: [], rows: [{ ticker: "AAA" }] }, ok())).toEqual({
    blocks: [{ kind: "sentence", text: EMPTY_READ }],
  });
  expect(
    portfolioBody(
      "movers",
      { rows: [{ ticker: "AAA", sleeve: "Core", scaled_weight_pct: 10, current_price: null, day_return_pct: 1, unrealized_pct: 2 }] },
      ok(),
    ).blocks,
  ).toEqual([
    {
      kind: "table",
      columns: ["ticker", "sleeve", "weight", "price", "day", "unrealized"],
      rows: [["AAA", "Core", "10", "—", "1", "2"]],
    },
  ]);
  expect(portfolioBody("movers", { rows: [] }, ok())).toEqual({ blocks: [{ kind: "sentence", text: EMPTY_READ }] });
  expect(
    portfolioBody(
      "book",
      { rows: [{ ticker: "AAA", weight_pct: 12, scaled_weight_pct: 10, entry_price: 5, current_price: null, unrealized_pct: 20 }] },
      ok(),
    ).blocks,
  ).toEqual([
    {
      kind: "table",
      columns: ["ticker", "weight", "scaled", "entry", "price", "unrealized"],
      rows: [["AAA", "12", "10", "5", "—", "20"]],
    },
  ]);
  expect(JSON.stringify(portfolioBody("book", { rows: [] }, ok()))).not.toContain("sleeve");
  expect(portfolioBody("book", { rows: [] }, ok())).toEqual({ blocks: [{ kind: "sentence", text: EMPTY_READ }] });
});

test("NAV charts two or more points and keeps the point table", () => {
  const one = portfolioBody(
    "nav",
    { points: [{ date: "2026-01-02", nav: 10, day_return_pct: null, contract: "finalized_accounting", index: 100 }] },
    ok(),
  );
  expect(one.blocks.map((block) => block.kind)).toEqual(["sentence", "table"]);
  expect(one.blocks[0]).toEqual({ kind: "sentence", text: EMPTY_READ });
  expect(one.blocks[1]).toEqual({
    kind: "table",
    columns: ["date", "nav", "day", "contract", "index"],
    rows: [["2026-01-02", "10", "—", "finalized_accounting", "100"]],
  });

  const two = portfolioBody(
    "nav",
    {
      points: [
        { date: "2026-01-01", nav: 10, day_return_pct: null, contract: "finalized_accounting", index: 100 },
        { date: "2026-01-02", nav: 30, day_return_pct: 1.5, contract: "finalized_accounting", index: 103 },
      ],
    },
    ok(),
  );
  expect(two.blocks.map((block) => block.kind)).toEqual(["chart", "table"]);
  expect(two.blocks[0]).toEqual({ kind: "chart", text: "▁█" });
  expect(JSON.stringify(two)).not.toContain(EMPTY_READ);

  const missing = portfolioBody(
    "nav",
    {
      points: [
        { date: "2026-01-01", nav: null },
        { date: "2026-01-02", nav: null },
      ],
    },
    ok(),
  );
  expect(missing.blocks.some((block) => block.kind === "chart")).toBe(false);
  expect(missing.blocks[0]).toEqual({ kind: "sentence", text: EMPTY_READ });

  expect(portfolioBody("nav", { points: [] }, ok())).toEqual({ blocks: [{ kind: "sentence", text: EMPTY_READ }] });

  const flat = portfolioBody(
    "nav",
    {
      points: [
        { date: "2026-01-01", nav: 5, day_return_pct: 0, contract: "finalized_accounting", index: 100 },
        { date: "2026-01-02", nav: 5, day_return_pct: 0, contract: "finalized_accounting", index: 100 },
      ],
    },
    ok(),
  );
  expect(flat.blocks[0]).toEqual({ kind: "chart", text: "▄▄" });
});

test("a long NAV series stays one row of the values it returned", () => {
  const points = Array.from({ length: 30 }, (_, index) => ({
    date: `2026-01-${String(index + 1).padStart(2, "0")}`,
    nav: index,
    day_return_pct: null,
    contract: "finalized_accounting",
    index,
  }));
  const body = portfolioBody("nav", { points }, ok());
  const line = body.blocks[0];
  expect(line?.kind).toBe("chart");
  if (line?.kind === "chart") {
    expect(line.text).toHaveLength(24);
    expect(line.text.startsWith("▁")).toBe(true);
    expect(line.text.endsWith("█")).toBe(true);
  }
  const table = body.blocks[1];
  expect(table?.kind).toBe("table");
  if (table?.kind === "table") expect(table.rows).toHaveLength(30);
});

test("drawdown is a stat, and a chart only when the series has values", () => {
  const body = portfolioBody(
    "drawdown",
    {
      max_pct: -12.5,
      current_pct: -1,
      series: [
        { t: "2026-01-01", v: -12.5 },
        { t: "2026-01-02", v: -1 },
      ],
    },
    ok(),
  );
  expect(body.blocks).toEqual([
    { kind: "stat", text: "max  -12.5   current  -1" },
    { kind: "chart", text: "▁█" },
  ]);
  expect(
    portfolioBody("drawdown", { max_pct: -3, current_pct: -3, series: [] }, ok()).blocks,
  ).toEqual([{ kind: "stat", text: "max  -3   current  -3" }]);
  expect(portfolioBody("drawdown", { max_pct: null, current_pct: null, series: [] }, ok())).toEqual({
    blocks: [{ kind: "sentence", text: EMPTY_READ }],
  });
  expect(portfolioBody("drawdown", { max_pct: null, current_pct: null, series: [{ t: "2026-01-01", v: null }] }, ok())).toEqual({
    blocks: [{ kind: "sentence", text: EMPTY_READ }],
  });
  const one = portfolioBody("drawdown", { max_pct: -2, current_pct: -2, series: [{ t: "2026-01-01", v: -2 }] }, ok());
  expect(one.blocks[1]).toEqual({ kind: "chart", text: "▄" });
});
