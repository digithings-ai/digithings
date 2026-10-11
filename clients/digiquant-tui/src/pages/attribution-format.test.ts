import { expect, test } from "bun:test";
import { EMPTY_READ, STUB_READ, type ReadResult } from "../read";
import { attributionBody } from "./attribution-format";

const ok = (lines: string[] = []): ReadResult => ({ status: "ok", lines, asOf: "2026-02-01" });

test("a stub, a missed API, and an empty read stay the exact sentence", () => {
  const missed = "/attribution: the official API could not be reached.";
  expect(attributionBody("attribution", null, { status: "error", lines: [missed], asOf: null })).toEqual({
    blocks: [{ kind: "sentence", text: missed }],
  });
  expect(
    attributionBody(
      "attribution",
      { sleeves: [{ sleeve: "Core", contribution_bp: 12 }], names: [{ ticker: "AAA", sleeve: "Core", contribution_bp: 12 }] },
      { status: "stub", lines: [STUB_READ], asOf: null },
    ),
  ).toEqual({
    blocks: [{ kind: "sentence", text: STUB_READ }],
  });
  expect(attributionBody("attribution", null, { status: "empty", lines: [EMPTY_READ], asOf: null })).toEqual({
    blocks: [{ kind: "sentence", text: EMPTY_READ }],
  });
});

test("sleeves and names are tables, and a missing contribution stays blank", () => {
  const body = attributionBody(
    "attribution",
    {
      window: { start: "2026-01-01", end: "2026-02-01" },
      sleeves: [
        { sleeve: "Core", contribution_bp: 12.5 },
        { sleeve: "Hedge", contribution_bp: null },
      ],
      names: [
        { ticker: "AAA", sleeve: "Core", contribution_bp: 12.5 },
        { ticker: "BBB", sleeve: null, contribution_bp: Number.NaN },
      ],
    },
    ok(["source  core:position_attribution"]),
  );
  expect(body.blocks).toEqual([
    { kind: "stat", text: "source  core:position_attribution" },
    {
      kind: "table",
      columns: ["sleeve", "bp"],
      rows: [
        ["Core", "12.5"],
        ["Hedge", "—"],
      ],
    },
    {
      kind: "table",
      columns: ["ticker", "sleeve", "bp"],
      rows: [
        ["AAA", "Core", "12.5"],
        ["BBB", "—", "—"],
      ],
    },
  ]);
  expect(JSON.stringify(body)).not.toContain("2026-01-01");
});

test("one list paints alone, and a null sleeve contribution is not summed from names", () => {
  expect(
    attributionBody(
      "attribution",
      {
        sleeves: [{ sleeve: "Core", contribution_bp: null }],
        names: [
          { ticker: "AAA", sleeve: "Core", contribution_bp: 10 },
          { ticker: "BBB", sleeve: "Core", contribution_bp: 5 },
        ],
      },
      ok(),
    ).blocks,
  ).toEqual([
    { kind: "table", columns: ["sleeve", "bp"], rows: [["Core", "—"]] },
    {
      kind: "table",
      columns: ["ticker", "sleeve", "bp"],
      rows: [
        ["AAA", "Core", "10"],
        ["BBB", "Core", "5"],
      ],
    },
  ]);
  expect(attributionBody("attribution", { sleeves: [], names: [{ ticker: "AAA", sleeve: "Core", contribution_bp: 3 }] }, ok())).toEqual({
    blocks: [{ kind: "table", columns: ["ticker", "sleeve", "bp"], rows: [["AAA", "Core", "3"]] }],
  });
  expect(attributionBody("attribution", { sleeves: [{ sleeve: "Core", contribution_bp: -2 }], names: [] }, ok())).toEqual({
    blocks: [{ kind: "table", columns: ["sleeve", "bp"], rows: [["Core", "-2"]] }],
  });
});

test("two empty lists stay the empty sentence and do not invent a row", () => {
  expect(
    attributionBody("attribution", { window: { start: "2026-01-01", end: "2026-02-01" }, sleeves: [], names: [] }, ok()),
  ).toEqual({
    blocks: [{ kind: "sentence", text: EMPTY_READ }],
  });
  expect(
    attributionBody(
      "attribution",
      { sleeves: [{ contribution_bp: 9 }], names: [{ sleeve: "Core", contribution_bp: 1 }] },
      ok(),
    ),
  ).toEqual({
    blocks: [{ kind: "sentence", text: EMPTY_READ }],
  });
  const text = JSON.stringify(
    attributionBody("attribution", { window: { start: "2026-01-01", end: "2026-02-01" }, sleeves: [], names: [] }, ok()),
  );
  expect(text).not.toContain("2026-01-01");
  expect(text).not.toContain("9");
});
