import { expect, test } from "bun:test";
import { EMPTY_READ, STUB_READ } from "../read";
import { shapeLines, strategyBlocks, tidyBody, tidyNumbers } from "./shape";

test("a stub, a 502, and an empty read stay the exact sentence", () => {
  expect(shapeLines([STUB_READ])).toEqual({ blocks: [{ kind: "sentence", text: STUB_READ }] });
  const failed = "/brief/decision failed (502): core supabase is not configured";
  expect(shapeLines([failed])).toEqual({ blocks: [{ kind: "sentence", text: failed }] });
  expect(shapeLines([EMPTY_READ])).toEqual({ blocks: [{ kind: "sentence", text: EMPTY_READ }] });
  expect(shapeLines(["no pairs"])).toEqual({ blocks: [{ kind: "sentence", text: "no pairs" }] });
});

test("summary fields become a stat line and the list becomes rows", () => {
  const body = shapeLines([
    "source  static-graph",
    "marks  unavailable",
    "run  —",
    "selected  ingest",
    "Ingest  collect  —  → research",
    "Research  research  —  → decide",
  ]);
  expect(body.blocks[0]).toEqual({
    kind: "stat",
    text: "source  static-graph   marks  unavailable   run  —   selected  ingest",
  });
  expect(body.blocks[1]).toEqual({
    kind: "table",
    columns: [],
    rows: [
      ["Ingest", "collect", "—", "→ research"],
      ["Research", "research", "—", "→ decide"],
    ],
  });
});

test("repeated keyed lines become a table with those keys as columns", () => {
  const body = shapeLines(["pair EURUSD  bid 1.1  offer 1.2", "pair USDJPY  bid 150  offer 150.2"]);
  expect(body.blocks).toEqual([
    {
      kind: "table",
      columns: ["pair", "bid", "offer"],
      rows: [
        ["EURUSD", "1.1", "1.2"],
        ["USDJPY", "150", "150.2"],
      ],
    },
  ]);
});

test("a name list is rows and does not invent a price", () => {
  const body = shapeLines(["EURUSD", "USDJPY"]);
  expect(body.blocks).toEqual([{ kind: "table", columns: [], rows: [["EURUSD"], ["USDJPY"]] }]);
  expect(JSON.stringify(body)).not.toContain("99.909");
});

test("strategy text stays a sentence and a catalog is a table", () => {
  expect(strategyBlocks({ type: "text", lines: [STUB_READ] }).blocks).toEqual([{ kind: "sentence", text: STUB_READ }]);
  const table = strategyBlocks({
    type: "table",
    head: ["ID", "Strategy"],
    rows: [["s1", "carry"]],
  });
  expect(table.blocks).toEqual([{ kind: "table", columns: ["ID", "Strategy"], rows: [["s1", "carry"]] }]);
});

test("long numbers are tidied; dates, times, versions and short numbers stay", () => {
  expect(tidyNumbers("NAV 1.39268400000001")).toBe("NAV 1.3927");
  expect(tidyNumbers("cash 1043280.123456")).toBe("cash 1043280.12");
  expect(tidyNumbers("vol 0.000123456789")).toBe("vol 0.0001235");
  expect(tidyNumbers("-2.500000000001%")).toBe("-2.5000%");
  expect(tidyNumbers("2026-10-12 09:30:00.123456 104.80 v1.2.345678")).toBe("2026-10-12 09:30:00.123456 104.80 v1.2.345678");
});

test("table cells and prose are tidied, charts are not", () => {
  const body = tidyBody({
    blocks: [
      { kind: "table", columns: ["Pair", "Mid"], rows: [["USDJPY", "149.123456789"]] },
      { kind: "stat", text: "beta 0.9876543" },
      { kind: "chart", text: "▁▂▃" },
    ],
  });
  expect(body.blocks).toEqual([
    { kind: "table", columns: ["Pair", "Mid"], rows: [["USDJPY", "149.1235"]] },
    { kind: "stat", text: "beta 0.9877" },
    { kind: "chart", text: "▁▂▃" },
  ]);
});
