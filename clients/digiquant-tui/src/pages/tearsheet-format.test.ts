import { expect, test } from "bun:test";
import { EMPTY_READ, STUB_READ, type ReadResult } from "../read";
import { tearsheetBody } from "./tearsheet-format";

const ok = (lines: string[] = []): ReadResult => ({ status: "ok", lines, asOf: "2026-02-01" });

test("a stub, a missed API, and an empty read stay the exact sentence", () => {
  const missed = "/performance: the official API could not be reached.";
  expect(tearsheetBody("performance", null, { status: "error", lines: [missed], asOf: null })).toEqual({
    blocks: [{ kind: "sentence", text: missed }],
  });
  expect(
    tearsheetBody(
      "performance",
      { metrics: { day_return_pct: 1.2, since_inception_pct: 3 } },
      { status: "stub", lines: [STUB_READ], asOf: null },
    ),
  ).toEqual({
    blocks: [{ kind: "sentence", text: STUB_READ }],
  });
  expect(tearsheetBody("navtable", null, { status: "empty", lines: [EMPTY_READ], asOf: null })).toEqual({
    blocks: [{ kind: "sentence", text: EMPTY_READ }],
  });
  const benchMissed = "/benchmarks: the official API could not be reached.";
  expect(
    tearsheetBody(
      "benchmarks",
      { series: { SPY: [{ date: "2026-01-02", close: 500 }] } },
      { status: "error", lines: [benchMissed], asOf: null },
    ),
  ).toEqual({
    blocks: [{ kind: "sentence", text: benchMissed }],
  });
});

test("performance is a stat of the returned metrics, and nulls are left out", () => {
  const body = tearsheetBody(
    "performance",
    {
      nav: {
        tip_date: "2026-02-01",
        base100_tip: 103.04,
        points: [
          { date: "2026-01-01", index: 100 },
          { date: "2026-02-01", index: 777 },
        ],
      },
      metrics: {
        day_return_pct: 1.2,
        since_inception_pct: 3.04,
        excess_return_pct: 0.4,
        alpha_pct: null,
        information_ratio: null,
        beta: 0.8,
        overlap_days: 20,
      },
      benchmark: { ticker: "SPY", aligned_start: "2026-01-15" },
      stale: { lag_days: 17, lag_direction: "metrics lag", metrics_as_of: "2026-01-31" },
      ssot: { bookWeightInvestedPct: 40.5 },
    },
    ok(["source  public_accounting_nav_history", "marks  stored"]),
  );
  expect(body.blocks).toEqual([
    { kind: "stat", text: "source  public_accounting_nav_history   marks  stored" },
    {
      kind: "stat",
      text: "day  1.2   since  3.04   excess  0.4   beta  0.8   overlap  20   NAV  103.04   date  2026-02-01   benchmark  SPY",
    },
  ]);
  const text = JSON.stringify(body);
  expect(text).not.toContain("777");
  expect(text).not.toContain("40.5");
  expect(text).not.toContain("17");
  expect(text).not.toContain("2026-01-15");
  expect(text).not.toContain("alpha");
  expect(body.blocks.some((block) => block.kind === "chart")).toBe(false);
});

test("a performance payload with no numbers stays the empty sentence", () => {
  expect(
    tearsheetBody(
      "performance",
      {
        nav: { tip_date: null, base100_tip: null, points: [] },
        metrics: {
          day_return_pct: null,
          since_inception_pct: null,
          excess_return_pct: null,
          alpha_pct: null,
          information_ratio: null,
          beta: null,
          overlap_days: null,
        },
        benchmark: { ticker: null, aligned_start: null },
      },
      ok(),
    ),
  ).toEqual({ blocks: [{ kind: "sentence", text: EMPTY_READ }] });
});

test("NAV is a table, and a chart only when two or more nav numbers are present", () => {
  const one = tearsheetBody(
    "navtable",
    {
      points: [{ date: "2026-01-02", nav: 10, day_return_pct: null, contract: "finalized_accounting", index: 100 }],
    },
    ok(),
  );
  expect(one.blocks).toEqual([
    {
      kind: "table",
      columns: ["date", "nav", "day", "contract", "index"],
      rows: [["2026-01-02", "10", "—", "finalized_accounting", "100"]],
    },
  ]);
  expect(JSON.stringify(one)).not.toContain(EMPTY_READ);
  expect(one.blocks.some((block) => block.kind === "chart")).toBe(false);

  const missing = tearsheetBody(
    "navtable",
    {
      points: [
        { date: "2026-01-01", nav: null, index: 100 },
        { date: "2026-01-02", nav: null, index: 110 },
      ],
    },
    ok(),
  );
  expect(missing.blocks.some((block) => block.kind === "chart")).toBe(false);
  expect(missing.blocks.map((block) => block.kind)).toEqual(["table"]);
  expect(JSON.stringify(missing)).not.toContain(EMPTY_READ);

  const two = tearsheetBody(
    "navtable",
    {
      points: [
        { date: "2026-01-01", nav: 10, day_return_pct: null, contract: "legacy_estimate", index: 100 },
        { date: "2026-01-02", nav: 30, day_return_pct: 1.5, contract: "finalized_accounting", index: 103 },
      ],
    },
    ok(["source  public_accounting_nav_history"]),
  );
  expect(two.blocks.map((block) => block.kind)).toEqual(["stat", "chart", "table"]);
  expect(two.blocks[1]).toEqual({ kind: "chart", text: "▁█" });
  expect(JSON.stringify(two)).not.toContain(EMPTY_READ);

  expect(tearsheetBody("navtable", { points: [] }, ok())).toEqual({
    blocks: [{ kind: "sentence", text: EMPTY_READ }],
  });
});

test("two equal nav numbers stay a chart of those numbers, not an extra invented point", () => {
  const flat = tearsheetBody(
    "navtable",
    {
      points: [
        { date: "2026-01-01", nav: 5, day_return_pct: 0, contract: "finalized_accounting", index: 100 },
        { date: "2026-01-02", nav: 5, day_return_pct: 0, contract: "finalized_accounting", index: 100 },
      ],
    },
    ok(),
  );
  expect(flat.blocks[0]).toEqual({ kind: "chart", text: "▄▄" });
  const table = flat.blocks[1];
  expect(table?.kind).toBe("table");
  if (table?.kind === "table") expect(table.rows).toHaveLength(2);
});

test("a long NAV series stays one row of the values it returned", () => {
  const points = Array.from({ length: 30 }, (_, index) => ({
    date: `2026-01-${String(index + 1).padStart(2, "0")}`,
    nav: index,
    day_return_pct: null,
    contract: "finalized_accounting",
    index,
  }));
  const body = tearsheetBody("navtable", { points }, ok());
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

test("benchmarks are a table of aligned closes, and an empty series stays the empty sentence", () => {
  const body = tearsheetBody(
    "benchmarks",
    {
      universe: ["SPY", "QQQ"],
      series: {
        SPY: [
          { date: "2026-01-01", close: 500 },
          { date: "2026-01-02", close: null },
        ],
        QQQ: [],
      },
      aligned_start: "2025-12-01",
      overlap_days: 42,
    },
    ok(["source  market_api"]),
  );
  expect(body.blocks).toEqual([
    { kind: "stat", text: "source  market_api" },
    {
      kind: "table",
      columns: ["ticker", "date", "close"],
      rows: [
        ["SPY", "2026-01-01", "500"],
        ["SPY", "2026-01-02", "—"],
      ],
    },
  ]);
  expect(JSON.stringify(body)).not.toContain("QQQ");
  expect(JSON.stringify(body)).not.toContain("42");
  expect(JSON.stringify(body)).not.toContain("2025-12-01");

  const empty = tearsheetBody(
    "benchmarks",
    { universe: ["SPY"], series: { SPY: [] }, aligned_start: null, overlap_days: 0 },
    ok(),
  );
  expect(empty).toEqual({ blocks: [{ kind: "sentence", text: EMPTY_READ }] });
  const text = JSON.stringify(empty);
  expect(text).not.toContain("SPY");
  expect(text).not.toContain("0");
});

test("the drawdown pane stays the line read and does not gain a chart", () => {
  const body = tearsheetBody(
    "drawdown",
    {
      max_pct: -12,
      current_pct: -1,
      series: [
        { t: "2026-01-01", v: -12 },
        { t: "2026-01-02", v: -9.5 },
      ],
    },
    ok(["max_pct  -12"]),
  );
  expect(body.blocks.some((block) => block.kind === "chart")).toBe(false);
  expect(JSON.stringify(body)).not.toContain("▁");
  expect(JSON.stringify(body)).toContain("max_pct");
  expect(JSON.stringify(body)).not.toContain("9.5");
});
