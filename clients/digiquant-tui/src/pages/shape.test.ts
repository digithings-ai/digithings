import { expect, test } from "bun:test";
import { EMPTY_READ, STUB_READ } from "../read";
import { shapeLines, strategyBlocks } from "./shape";

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
