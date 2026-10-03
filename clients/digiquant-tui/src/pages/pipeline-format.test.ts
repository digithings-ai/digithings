import { expect, test } from "bun:test";
import { EMPTY_READ, STUB_READ, type ReadResult } from "../read";
import { pipelineBody } from "./pipeline-format";

const ok = (lines: string[] = []): ReadResult => ({ status: "ok", lines, asOf: "2026-02-01" });
const NO_NODES = "No nodes in this read.";

test("a stub, a missed API, and an empty read stay the exact sentence", () => {
  const missed = "/pipeline/runs/latest/health: the official API could not be reached.";
  expect(pipelineBody("pl-run-health", null, { status: "error", lines: [missed], asOf: null })).toEqual({
    blocks: [{ kind: "sentence", text: missed }],
  });
  expect(
    pipelineBody(
      "pl-narrative",
      { heading: "Why", paragraphs: ["because"] },
      { status: "stub", lines: [STUB_READ], asOf: null },
    ),
  ).toEqual({
    blocks: [{ kind: "sentence", text: STUB_READ }],
  });
  expect(pipelineBody("pl-artifacts", null, { status: "empty", lines: [EMPTY_READ], asOf: null })).toEqual({
    blocks: [{ kind: "sentence", text: EMPTY_READ }],
  });
  expect(pipelineBody("pl-canvas", { nodes: [] }, { status: "empty", lines: [NO_NODES], asOf: null })).toEqual({
    blocks: [{ kind: "sentence", text: NO_NODES }],
  });
  const traceMissed = "/pipeline/runs/latest/trace: the official API could not be reached.";
  expect(
    pipelineBody("pl-call-trace", { rows: [{ node: "ingest", calls: 3 }] }, { status: "error", lines: [traceMissed], asOf: null }),
  ).toEqual({
    blocks: [{ kind: "sentence", text: traceMissed }],
  });
});

test("run health is a stat of the returned fields, or the empty sentence", () => {
  const body = pipelineBody(
    "pl-run-health",
    {
      run_date: "2026-02-01",
      run_type: "daily",
      status: "ok",
      config: "gpt",
      posture: null,
      nodes: { ok: 3, carried: 1, failed: 0 },
      inputs_calls: { persisted: null, note: "call counts are not on run_health" },
      calls: null,
      tokens_in: 12,
      tokens_out: null,
      cost_usd: null,
      invented: 99,
    },
    ok(["source  core:run_health", "marks  stored"]),
  );
  expect(body.blocks).toEqual([
    { kind: "stat", text: "source  core:run_health   marks  stored" },
    {
      kind: "stat",
      text: "run  2026-02-01   type  daily   status  ok   config  gpt   ok  3   carried  1   failed  0   tokens in  12",
    },
  ]);
  const text = JSON.stringify(body);
  expect(text).not.toContain("call counts");
  expect(text).not.toContain("invented");
  expect(text).not.toContain("99");
  expect(
    pipelineBody(
      "pl-run-health",
      {
        run_date: null,
        run_type: null,
        status: null,
        config: null,
        posture: null,
        nodes: null,
        inputs_calls: { persisted: null, note: "call counts are not on run_health" },
        calls: null,
        tokens_in: null,
        tokens_out: null,
        cost_usd: null,
      },
      ok(),
    ),
  ).toEqual({ blocks: [{ kind: "sentence", text: EMPTY_READ }] });
});

test("the narrative is the heading and paragraphs, or the empty sentence", () => {
  const body = pipelineBody(
    "pl-narrative",
    { run_date: "2026-02-01", heading: "Why today", paragraphs: ["Rates moved.", ""], extra: "not a paragraph" },
    ok(["source  core:documents"]),
  );
  expect(body.blocks).toEqual([{ kind: "sentence", text: "Why today\nRates moved." }]);
  expect(JSON.stringify(body)).not.toContain("not a paragraph");
  expect(pipelineBody("pl-narrative", { run_date: "2026-02-01", heading: null, paragraphs: [] }, ok())).toEqual({
    blocks: [{ kind: "sentence", text: EMPTY_READ }],
  });
});

test("artifacts are a table of returned rows, or the empty sentence", () => {
  const body = pipelineBody(
    "pl-artifacts",
    {
      rows: [
        { stage: "research", node: "decide", document: "note", date: "2026-02-01", state_only: false },
        { stage: null, node: "", document: "skip", date: null },
        { stage: null, node: "publish", document: null, date: null, state_only: true },
      ],
      invented: [{ node: "ghost" }],
    },
    ok(["source  core:documents"]),
  );
  expect(body.blocks).toEqual([
    { kind: "stat", text: "source  core:documents" },
    {
      kind: "table",
      columns: ["stage", "node", "document", "date"],
      rows: [
        ["research", "decide", "note", "2026-02-01"],
        ["—", "publish", "—", "—"],
      ],
    },
  ]);
  expect(JSON.stringify(body)).not.toContain("ghost");
  expect(JSON.stringify(body)).not.toContain("skip");
  expect(pipelineBody("pl-artifacts", { rows: [] }, ok())).toEqual({
    blocks: [{ kind: "sentence", text: EMPTY_READ }],
  });
});

test("the graph is a node table, never a canvas, or the empty sentence", () => {
  const body = pipelineBody(
    "pl-canvas",
    {
      run_date: "2026-02-01",
      selected_node: "decide",
      nodes: [
        { id: "research", label: "Research", stage: "research", col: 1, state: "ok", to: ["decide"] },
        { id: "decide", label: "Decide", stage: null, col: 2, state: null, to: [] },
      ],
    },
    ok(["source  core:node_runs", "marks  stored"]),
  );
  expect(body.blocks).toEqual([
    { kind: "stat", text: "source  core:node_runs   marks  stored" },
    { kind: "stat", text: "run  2026-02-01   selected  decide" },
    {
      kind: "table",
      columns: ["node", "stage", "state", "to"],
      rows: [
        ["Research", "research", "ok", "decide"],
        ["Decide", "—", "—", "—"],
      ],
    },
  ]);
  expect(body.blocks.some((block) => block.kind === "chart")).toBe(false);
  expect(JSON.stringify(body)).not.toContain("canvas");
  expect(JSON.stringify(body)).not.toContain("Ingest");
  expect(JSON.stringify(body)).not.toContain("Publish");
  expect(pipelineBody("pl-canvas", { run_date: null, selected_node: null, nodes: [] }, ok())).toEqual({
    blocks: [{ kind: "sentence", text: NO_NODES }],
  });
});

test("the node document is its text, or the empty sentence", () => {
  const body = pipelineBody(
    "pl-node-document",
    {
      run_date: "2026-02-01",
      node_id: "decide",
      title: "Decide",
      paragraphs: ["Held the book."],
      note: null,
    },
    ok(),
  );
  expect(body.blocks).toEqual([{ kind: "sentence", text: "Decide\nHeld the book." }]);
  expect(
    pipelineBody(
      "pl-node-document",
      { run_date: null, node_id: "selected", title: null, paragraphs: [], note: "no document for this node" },
      ok(),
    ),
  ).toEqual({ blocks: [{ kind: "sentence", text: EMPTY_READ }] });
});

test("the call trace is a table of returned rows, or the empty sentence", () => {
  const body = pipelineBody(
    "pl-call-trace",
    {
      rows: [
        { node: "research", calls: 2, duration_s: 1.5, state: "ok" },
        { node: "", calls: 9, duration_s: 4, state: "failed" },
        { node: "publish", calls: null, duration_s: null, state: null },
      ],
    },
    ok(["source  core:run_event_trace"]),
  );
  expect(body.blocks).toEqual([
    { kind: "stat", text: "source  core:run_event_trace" },
    {
      kind: "table",
      columns: ["node", "calls", "duration", "state"],
      rows: [
        ["research", "2", "1.5", "ok"],
        ["publish", "—", "—", "—"],
      ],
    },
  ]);
  expect(JSON.stringify(body)).not.toContain("failed");
  expect(pipelineBody("pl-call-trace", { rows: [] }, ok())).toEqual({
    blocks: [{ kind: "sentence", text: EMPTY_READ }],
  });
});
