import { expect, test } from "bun:test";
import { EMPTY_READ, STUB_READ, type ReadResult } from "../read";
import { thesesBody } from "./theses-format";

const ok = (lines: string[] = []): ReadResult => ({ status: "ok", lines, asOf: "2026-02-01" });

test("a stub, a missed API, and an empty read stay the exact sentence", () => {
  const missed = "/theses: the official API could not be reached.";
  expect(thesesBody("theses", null, { status: "error", lines: [missed], asOf: null })).toEqual({
    blocks: [{ kind: "sentence", text: missed }],
  });
  expect(
    thesesBody(
      "theses",
      {
        counts: { active: 1, watch: 0, exited: 0 },
        theses: [{ id: "t1", name: "Gold", state: "active", vehicles: ["GLD"] }],
      },
      { status: "stub", lines: [STUB_READ], asOf: null },
    ),
  ).toEqual({
    blocks: [{ kind: "sentence", text: STUB_READ }],
  });
  expect(thesesBody("signals", null, { status: "empty", lines: [EMPTY_READ], asOf: null })).toEqual({
    blocks: [{ kind: "sentence", text: EMPTY_READ }],
  });
  const signalMissed = "/theses/signals: the official API could not be reached.";
  expect(
    thesesBody(
      "signals",
      { theses: [{ id: "a", name: "A", state: "watch", note: "resolve" }] },
      { status: "error", lines: [signalMissed], asOf: null },
    ),
  ).toEqual({
    blocks: [{ kind: "sentence", text: signalMissed }],
  });
});

test("theses are a counts stat, then the thesis table", () => {
  const body = thesesBody(
    "theses",
    {
      counts: { active: 1, watch: 0, exited: 2 },
      theses: [
        {
          id: "t1",
          name: "Gold",
          state: "active",
          vehicles: ["GLD", "IAU"],
          evidence: "real rates",
          kill_condition: "yields fall",
          note: "not on this table",
        },
        {
          id: "t2",
          name: "Banks",
          state: "exited",
          vehicles: [],
          evidence: null,
          kill_condition: null,
          note: null,
        },
      ],
      extra: 99,
    },
    ok(["source  core:theses", "marks  stored"]),
  );
  expect(body.blocks).toEqual([
    { kind: "stat", text: "source  core:theses   marks  stored" },
    { kind: "stat", text: "active  1   watch  0   exited  2" },
    {
      kind: "table",
      columns: ["id", "thesis", "state", "vehicles", "evidence", "kill"],
      rows: [
        ["t1", "Gold", "active", "GLD IAU", "real rates", "yields fall"],
        ["t2", "Banks", "exited", "—", "—", "—"],
      ],
    },
  ]);
  const text = JSON.stringify(body);
  expect(text).not.toContain("99");
  expect(text).not.toContain("not on this table");
  expect(body.blocks.some((block) => block.kind === "chart")).toBe(false);
});

test("a missing count is left out and is not replaced with a row tally", () => {
  const body = thesesBody(
    "theses",
    {
      counts: { active: 4, watch: null, exited: 0 },
      theses: [{ id: "t1", name: "Gold", state: "active", vehicles: ["GLD"], evidence: null, kill_condition: null }],
    },
    ok(),
  );
  expect(body.blocks[0]).toEqual({ kind: "stat", text: "active  4   exited  0" });
  expect(JSON.stringify(body.blocks[0])).not.toContain("watch");
  expect(body.blocks[1]).toMatchObject({ kind: "table", rows: [["t1", "Gold", "active", "GLD", "—", "—"]] });
});

test("an empty thesis list stays the empty sentence and does not invent counts", () => {
  const body = thesesBody(
    "theses",
    { counts: { active: 0, watch: 0, exited: 0 }, theses: [] },
    ok(["source  core:theses"]),
  );
  expect(body).toEqual({ blocks: [{ kind: "sentence", text: EMPTY_READ }] });
  expect(JSON.stringify(body)).not.toContain("0");
  expect(thesesBody("theses", { counts: { active: 3 }, theses: [{ name: "Gold", state: "active" }] }, ok())).toEqual({
    blocks: [{ kind: "sentence", text: EMPTY_READ }],
  });
});

test("signals are a table, and an empty list stays the empty sentence", () => {
  const body = thesesBody(
    "signals",
    {
      counts: { active: 1, watch: 1, exited: 0 },
      theses: [
        { id: "a", name: "Gold", state: "active", vehicles: ["GLD"], evidence: "skip", kill_condition: "skip", note: "resolve" },
        { id: "b", name: "Banks", state: "watch", note: null },
      ],
    },
    ok(["source  core:theses"]),
  );
  expect(body.blocks).toEqual([
    { kind: "stat", text: "source  core:theses" },
    {
      kind: "table",
      columns: ["id", "thesis", "state", "note"],
      rows: [
        ["a", "Gold", "active", "resolve"],
        ["b", "Banks", "watch", "—"],
      ],
    },
  ]);
  const text = JSON.stringify(body);
  expect(text).not.toContain("active  1");
  expect(text).not.toContain("GLD");
  expect(text).not.toContain("skip");
  expect(thesesBody("signals", { counts: { active: 2 }, theses: [] }, ok())).toEqual({
    blocks: [{ kind: "sentence", text: EMPTY_READ }],
  });
});

test("another pane stays the line read", () => {
  const lines = ["counts  active  1", "theses  1. id t1"];
  const body = thesesBody("brief", { counts: { active: 1 }, theses: [{ id: "t1", name: "Gold" }] }, ok(lines));
  const text = JSON.stringify(body);
  expect(text).toContain("counts");
  expect(text).toContain("t1");
  expect(text).not.toContain("Gold");
  expect(text).not.toContain("vehicles");
  expect(body.blocks.some((block) => block.kind === "chart")).toBe(false);
  expect(body.blocks.some((block) => block.kind === "table" && block.columns.includes("thesis"))).toBe(false);
});
