import { expect, test } from "bun:test";
import { EMPTY_READ, STUB_READ, type ReadResult } from "../read";
import { briefBlocks } from "./brief-format";

const ok = (lines: string[] = []): ReadResult => ({ status: "ok", lines, asOf: "2026-01-02" });

test("a stub, a missed API, and an empty read stay the exact sentence", () => {
  const missed = "/brief: the official API could not be reached.";
  expect(briefBlocks("brief", null, { status: "error", lines: [missed], asOf: null })).toEqual({
    blocks: [{ kind: "sentence", text: missed }],
  });
  expect(briefBlocks("brief", { nav_tip: { nav: 1 } }, { status: "stub", lines: [STUB_READ], asOf: null })).toEqual({
    blocks: [{ kind: "sentence", text: STUB_READ }],
  });
  expect(briefBlocks("brief", null, { status: "empty", lines: [EMPTY_READ], asOf: null })).toEqual({
    blocks: [{ kind: "sentence", text: EMPTY_READ }],
  });
});

test("the scoreboard is a stat and session rows, with no invented event", () => {
  const body = briefBlocks(
    "brief",
    {
      nav_tip: { date: "2026-01-02", nav: 101.2, contract: "finalized_accounting" },
      day_return_pct: 0.4,
      since_inception_pct: null,
      invested_pct: 80,
      overlay: { active: false, live_vs_mark_pct: 0, badge: "finalized" },
      session_events: [],
    },
    ok(["source  public_accounting_nav_history"]),
  );
  expect(body.blocks[0]).toEqual({ kind: "stat", text: "source  public_accounting_nav_history" });
  expect(body.blocks[1]).toEqual({
    kind: "stat",
    text: "NAV  101.2   date  2026-01-02   contract  finalized_accounting   day  0.4   invested  80   overlay  finalized   vs mark  0",
  });
  expect(body.blocks.some((block) => block.kind === "table")).toBe(false);
  expect(JSON.stringify(body)).not.toContain("99.909");
  expect(JSON.stringify(body)).not.toContain("204.04");
});

test("a session row is a table and a missing book stays the empty sentence", () => {
  const row = briefBlocks(
    "brief",
    {
      nav_tip: null,
      session_events: [{ date: "2026-01-02", ticker: "AAA", event: "OPEN", weight_pct: 2 }],
    },
    ok(),
  );
  expect(row.blocks).toEqual([
    {
      kind: "table",
      columns: ["date", "ticker", "event", "weight"],
      rows: [["2026-01-02", "AAA", "OPEN", "2"]],
    },
  ]);
  expect(
    briefBlocks("decision", { decision: null }, ok()),
  ).toEqual({ blocks: [{ kind: "sentence", text: EMPTY_READ }] });
  expect(briefBlocks("signals", { theses: [], counts: { active: 0, watch: 0, exited: 0 } }, ok())).toEqual({
    blocks: [{ kind: "sentence", text: EMPTY_READ }],
  });
  expect(briefBlocks("risks", { risks: [] }, ok())).toEqual({ blocks: [{ kind: "sentence", text: EMPTY_READ }] });
  expect(briefBlocks("movers", { rows: [] }, ok())).toEqual({ blocks: [{ kind: "sentence", text: EMPTY_READ }] });
  expect(
    briefBlocks("pl-run-health", { run_date: null, run_type: null, status: null, config: null, nodes: null }, ok()),
  ).toEqual({ blocks: [{ kind: "sentence", text: EMPTY_READ }] });
});

test("live marks and movers use only the fields the read returned", () => {
  const live = briefBlocks(
    "live",
    {
      quote_date: "2026-01-02",
      live_vs_mark_pct: 0.1,
      day_return_live_pct: null,
      since_inception_live_pct: null,
      excess_live_pct: null,
      overlay_eligible: false,
      universe: ["AAA"],
    },
    ok(),
  );
  expect(live.blocks[0]?.kind).toBe("stat");
  expect(live.blocks[1]).toEqual({ kind: "table", columns: ["symbol"], rows: [["AAA"]] });
  const movers = briefBlocks(
    "movers",
    { rows: [{ ticker: "AAA", sleeve: "book", scaled_weight_pct: 10, current_price: null, day_return_pct: null }] },
    ok(),
  );
  expect(movers.blocks).toEqual([
    {
      kind: "table",
      columns: ["ticker", "sleeve", "weight", "price", "day", "unrealized"],
      rows: [["AAA", "book", "10", "—", "—", "—"]],
    },
  ]);
});
