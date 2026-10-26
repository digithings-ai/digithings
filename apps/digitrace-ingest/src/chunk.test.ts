import { describe, expect, it } from "vitest";
import { MAX_NDJSON_BYTES, MAX_SPAN_LINE_BYTES, chunkSpans } from "./chunk";
import type { SpanRecord } from "./types";

const TRACE = "0af7651916cd43dd8448eb211c80319c";

const meta = {
  batchId: "batch-1",
  tenant: "digithings",
  tenantSlugVerified: false,
  source: "digitrace-digichat",
  receivedAt: "2026-10-26T12:34:56.000Z",
};

function record(spanId: string, name = "GET /chat", padding = ""): SpanRecord {
  return {
    resource: { attributes: [{ key: "service.name", value: { stringValue: "digichat" } }] },
    scope: { name: "scope.a" },
    span: {
      traceId: TRACE,
      spanId,
      name,
      startTimeUnixNano: "1700000000000000000",
      endTimeUnixNano: "1700000000120000000",
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
