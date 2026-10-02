import { expect, test } from "bun:test";
import { DASH, EMPTY_READ, STUB_READ, fieldLines, graphLines, isEmptyPayload, isStubEnvelope, presentResponse } from "./read";

test("stub fingerprints are withheld, including the fixture ledger", () => {
  expect(isStubEnvelope({ data: { nav: 99.909 } })).toBe(true);
  expect(isStubEnvelope({ data: { nav: 204.04 } })).toBe(true);
  expect(isStubEnvelope({ data: { contract: "legacy_estimate" } })).toBe(true);
  expect(
    isStubEnvelope({
      data: {
        events: [
          { date: "2026-09-03", ticker: "XLF", type: "TRIM", fill_price: 54.1 },
          { date: "2026-06-01", ticker: "GLD", type: "OPEN", fill_price: 180 },
        ],
      },
    }),
  ).toBe(true);
  expect(isStubEnvelope({ data: { events: [{ date: "2024-01-02", ticker: "AAPL", fill_price: 10 }] } })).toBe(false);
});

test("missing fields are an em dash and an empty payload stays empty", () => {
  expect(fieldLines({ book_as_of: null, rows: [] })).toEqual([`book_as_of  ${DASH}`, "rows  no rows"]);
  expect(isEmptyPayload({ book_as_of: null, rows: [] })).toBe(true);
  expect(fieldLines({ events: [] })).toEqual(["events  no rows"]);
  expect(fieldLines({})).toEqual([EMPTY_READ]);
  expect(fieldLines({ name: null, weight_pct: 12.5 })).toEqual([`name  ${DASH}`, "weight_pct  12.5"]);
  expect(fieldLines({ flagged: false, level: null })).toEqual(["flagged  false", `level  ${DASH}`]);
  expect(fieldLines({ note: "open", events: [] })).toEqual(["note  open", "events  no rows"]);
});

test("a presented stub envelope does not paint the house book", () => {
  const stub = presentResponse("/brief", 200, { data: { nav: 99.909, contract: "legacy_estimate" } }, "fields");
  expect(stub.status).toBe("stub");
  expect(stub.lines).toEqual([STUB_READ]);
  expect(stub.lines.join(" ")).not.toContain("99.909");
  const ledger = presentResponse(
    "/ledger?limit=50",
    200,
    {
      data: {
        events: [
          { date: "2026-09-03", ticker: "XLF", type: "TRIM", fill_price: 54.1 },
          { date: "2026-06-01", ticker: "GLD", type: "OPEN", fill_price: 180 },
        ],
      },
    },
    "fields",
  );
  expect(ledger.status).toBe("stub");
  expect(ledger.lines.join(" ")).not.toContain("XLF");
  const missing = presentResponse("/rates/watchlist", 200, { data: { names: [] }, provenance: { source: "core:macro_series_observations" } }, "fields");
  expect(missing.status).toBe("empty");
  expect(missing.lines).toContain("names  no rows");
});

test("a pipeline graph is a node list", () => {
  expect(graphLines({ run_date: null, selected_node: null, nodes: [] })[2]).toBe("No nodes in this read.");
  const lines = graphLines({
    run_date: "2026-01-01",
    selected_node: "learn",
    nodes: [{ id: "in", label: "Inputs", stage: "ingest", state: "ok", to: ["learn"] }],
  });
  expect(lines[2]).toBe("Inputs  ingest  ok  → learn");
  expect(lines.join(" ")).not.toContain(STUB_READ);
});
