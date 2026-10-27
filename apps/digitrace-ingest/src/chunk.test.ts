import { describe, expect, it } from "vitest";
import { MAX_NDJSON_BYTES, MAX_SPAN_LINE_BYTES, chunkSpans } from "./chunk";
import { indexRows } from "./index-rows";
import type { SpanRecord } from "./types";

const TRACE = "0af7651916cd43dd8448eb211c80319c";

const meta = {
  batchId: "batch-1",
  tenant: "digithings",
  tenantSlugVerified: false,
  source: "digitrace-digichat",
  receivedAt: "2026-10-26T12:34:56.000Z",
};

function record(
  spanId: string,
  name = "GET /chat",
  padding = "",
  traceId = TRACE,
  start = "1700000000000000000",
  end = "1700000000120000000",
): SpanRecord {
  return {
    resource: { attributes: [{ key: "service.name", value: { stringValue: "digichat" } }] },
    scope: { name: "scope.a" },
    span: {
      traceId,
      spanId,
      name,
      startTimeUnixNano: start,
      endTimeUnixNano: end,
      attributes: padding === "" ? [] : [{ key: "blob", value: { stringValue: padding } }],
    },
  };
}

describe("chunkSpans", () => {
  it("turns one span into one archive message", () => {
    const { messages, droppedOversizedSpans } = chunkSpans(
      [record("b7ad6b7169203331")],
      meta,
      () => "uuid-1",
    );
    expect(droppedOversizedSpans).toBe(0);
    expect(messages).toHaveLength(1);
    expect(messages[0]).toMatchObject({
      v: 1,
      batchId: "batch-1",
      chunk: 0,
      chunks: 1,
      tenant: "digithings",
      tenantSlugVerified: false,
      source: "digitrace-digichat",
      archiveKey: "tenant=digithings/date=2026-10-26/digitrace-digichat/uuid-1.ndjson",
    });
    const line = JSON.parse(messages[0].ndjson.trim());
    expect(line.span.spanId).toBe("b7ad6b7169203331");
    expect(line.tenant_slug).toBe("digithings");
    expect(line.tenant_slug_verified).toBe(false);
    expect(line.chunk).toBe(0);
    expect(line.chunks).toBe(1);
  });

  it("enqueues nothing for an empty batch", () => {
    expect(chunkSpans([], meta)).toEqual({ messages: [], droppedOversizedSpans: 0 });
  });

  it("splits a large batch and keeps every record exactly once", () => {
    const records = Array.from({ length: 300 }, (_, index) =>
      record(index.toString(16).padStart(16, "0"), `span-${index}`, "x".repeat(500)),
    );
    let counter = 0;
    const { messages, droppedOversizedSpans } = chunkSpans(
      records,
      meta,
      () => `uuid-${counter++}`,
    );

    expect(droppedOversizedSpans).toBe(0);
    expect(messages.length).toBeGreaterThan(1);
    expect(messages.map((message) => message.chunk)).toEqual(messages.map((_, index) => index));
    expect(messages.every((message) => message.chunks === messages.length)).toBe(true);
    expect(new Set(messages.map((message) => message.archiveKey)).size).toBe(messages.length);

    const spanIds: string[] = [];
    for (const message of messages) {
      expect(new TextEncoder().encode(message.ndjson).byteLength).toBeLessThanOrEqual(
        MAX_NDJSON_BYTES,
      );
      for (const line of message.ndjson.trim().split("\n")) {
        spanIds.push(JSON.parse(line).span.spanId);
      }
    }
    expect(spanIds).toHaveLength(records.length);
    expect(new Set(spanIds).size).toBe(records.length);
  });

  it("never splits one trace across two messages, however the records are ordered", () => {
    // Two traces with their spans interleaved, the shape a byte-only packer
    // cuts in half: 45 KiB each, so the 56 KiB boundary would land inside the
    // first trace. The `digitrace_traces` row is a cross-span aggregate, so a
    // message boundary here would let the later slice replace the row.
    const traceA = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
    const traceB = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
    const padding = "x".repeat(9 * 1024);
    const records: SpanRecord[] = [];
    for (let index = 0; index < 5; index += 1) {
      records.push(record(`a${index}`, `a-${index}`, padding, traceA));
      records.push(record(`b${index}`, `b-${index}`, padding, traceB));
    }

    const { messages } = chunkSpans(records, meta);

    expect(messages.length).toBeGreaterThan(1);
    const homes = new Map<string, number>();
    messages.forEach((message, position) => {
      for (const line of message.ndjson.trim().split("\n")) {
        const { traceId } = JSON.parse(line).span as { traceId: string };
        const first = homes.get(traceId);
        if (first === undefined) homes.set(traceId, position);
        else expect(first).toBe(position);
      }
      // Neither trace exceeds the budget alone, so neither is marked partial.
      expect(message.incompleteTraces).toBeUndefined();
    });
    expect([...homes.keys()].sort()).toEqual([traceA, traceB]);
  });

  it("marks a trace too large for one message instead of splitting it silently", () => {
    // One trace alone above the budget: it has to cross a boundary, so every
    // message carrying part of it says so and the consumer writes no aggregate.
    const records = Array.from({ length: 4 }, (_, index) =>
      record(`000000000000000${index}`, `span-${index}`, "x".repeat(24 * 1024)),
    );

    const { messages } = chunkSpans(records, meta);

    expect(messages.length).toBeGreaterThan(1);
    for (const message of messages) {
      expect(message.incompleteTraces).toEqual([TRACE]);
    }
  });

  it("keeps a complete trace whole and lets its row be the union of all its spans", () => {
    // The review's probe, as a fixture: five spans of one trace at 1.0-2.6 s.
    const base = 1_700_000_000_000_000_000n;
    const at = (offsetMs: number) => (base + BigInt(offsetMs) * 1_000_000n).toString();
    const records = [
      record("0000000000000001", "root", "", TRACE, at(0), at(500)),
      record("0000000000000002", "child-1", "", TRACE, at(200), at(800)),
      record("0000000000000003", "child-2", "", TRACE, at(500), at(1_000)),
      record("0000000000000004", "child-3", "", TRACE, at(1_100), at(1_400)),
      record("0000000000000005", "child-4", "", TRACE, at(1_200), at(1_600)),
    ];

    const { messages } = chunkSpans(records, meta, () => "uuid-1");
    expect(messages).toHaveLength(1);
    expect(messages[0].incompleteTraces).toBeUndefined();

    const parsed = messages[0].ndjson
      .trim()
      .split("\n")
      .map((line) => JSON.parse(line));
    const spans = parsed.map((line) => ({
      resource: line.resource,
      scope: line.scope,
      span: line.span,
    }));
    const { traces } = indexRows(
      spans,
      "11111111-2222-3333-4444-555555555555",
      meta.receivedAt,
      meta.source,
    );

    expect(traces).toHaveLength(1);
    expect(traces[0]).toMatchObject({
      trace_id: TRACE,
      span_count: 5,
      started_at: "2023-11-14T22:13:20.000Z",
      ended_at: "2023-11-14T22:13:21.600Z",
      duration_ms: 1600,
      name: "root",
    });
    // Replaying the same message must not change the row.
    expect(
      indexRows(spans, "11111111-2222-3333-4444-555555555555", meta.receivedAt, meta.source).traces,
    ).toEqual(traces);
  });

  it("drops a span too large for one queue message, and counts it", () => {
    const huge = "x".repeat(MAX_SPAN_LINE_BYTES);
    const { messages, droppedOversizedSpans } = chunkSpans(
      [record("0000000000000001"), record("0000000000000002", "huge", huge)],
      meta,
    );
    expect(droppedOversizedSpans).toBe(1);
    const lines = messages.flatMap((message) => message.ndjson.trim().split("\n"));
    expect(lines).toHaveLength(1);
    expect(JSON.parse(lines[0]).span.spanId).toBe("0000000000000001");
  });

  it("puts the archive date in the UTC partition of the receive time", () => {
    const { messages } = chunkSpans([record("0000000000000001")], {
      ...meta,
      receivedAt: "2026-10-26T23:59:59.999Z",
    });
    expect(messages[0].archiveKey).toContain("date=2026-10-26");
  });
});
