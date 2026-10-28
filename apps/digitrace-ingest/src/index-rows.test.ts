import { describe, expect, it } from "vitest";
import { CONFLICT_TARGETS, indexRows, isoFromNanos, __internal } from "./index-rows";
import type { SpanRecord } from "./types";

const TRACE = "0af7651916cd43dd8448eb211c80319c";
const WORKSPACE = "11111111-2222-3333-4444-555555555555";
const RECEIVED = "2026-10-26T12:00:00.000Z";
const SOURCE = "digitrace-digichat";

function record(
  spanId: string,
  overrides: Partial<SpanRecord["span"]> = {},
  resourceAttributes: SpanRecord["resource"]["attributes"] = [
    { key: "service.name", value: { stringValue: "digichat" } },
  ],
): SpanRecord {
  return {
    resource: { attributes: resourceAttributes },
    scope: { name: "digitrace.test", version: "1.0.0" },
    span: {
      traceId: TRACE,
      spanId,
      name: "GET /chat",
      startTimeUnixNano: "1700000000000000000",
      endTimeUnixNano: "1700000000120000000",
      kind: 2,
      attributes: [],
      ...overrides,
    },
  };
}

describe("isoFromNanos", () => {
  it("converts OTLP nanoseconds to an ISO timestamp", () => {
    expect(isoFromNanos("1700000000120000000")).toBe("2023-11-14T22:13:20.120Z");
    expect(isoFromNanos(1_700_000_000_120_000_000)).toBe("2023-11-14T22:13:20.120Z");
  });

  it("returns null for a missing or unusable value", () => {
    expect(isoFromNanos(undefined)).toBeNull();
    expect(isoFromNanos("")).toBeNull();
    expect(isoFromNanos("not-a-number")).toBeNull();
  });
});

describe("indexRows", () => {
  it("returns nothing for nothing", () => {
    expect(indexRows([], WORKSPACE, RECEIVED, SOURCE)).toEqual({ spans: [], traces: [] });
  });

  it("writes exactly the columns the index migration defines", () => {
    // Pinned to migrations/0001_digitrace_index.sql.
    // A column that is not there is a runtime 400, so the name list is the test.
    const rows = indexRows([record("b7ad6b7169203331")], WORKSPACE, RECEIVED, SOURCE);

    expect(Object.keys(rows.spans[0]).sort()).toEqual(
      [
        "attributes",
        "cost_usd",
        "duration_ms",
        "ended_at",
        "input_hash",
        "input_length",
        "input_tokens",
        "kind",
        "model",
        "name",
        "output_hash",
        "output_length",
        "output_tokens",
        "parent_span_id",
        "provider",
        "run_id",
        "session_id",
        "span_id",
        "started_at",
        "status",
        "status_message",
        "total_tokens",
        "trace_id",
        "workspace_id",
      ].sort(),
    );
    expect(Object.keys(rows.traces[0]).sort()).toEqual(
      [
        "attributes",
        "duration_ms",
        "ended_at",
        "name",
        "resource",
        "run_id",
        "service_name",
        "session_id",
        "source",
        "span_count",
        "started_at",
        "status",
        "status_message",
        "trace_id",
        "workspace_id",
      ].sort(),
    );
  });

  it("writes a span row with the workspace, and no tenant slug", () => {
    const rows = indexRows([record("b7ad6b7169203331")], WORKSPACE, RECEIVED, SOURCE);
    const [span] = rows.spans;
    expect(span).toMatchObject({
      workspace_id: WORKSPACE,
      trace_id: TRACE,
      span_id: "b7ad6b7169203331",
      parent_span_id: null,
      name: "GET /chat",
      kind: "SPAN_KIND_SERVER",
      status: "STATUS_CODE_UNSET",
      status_message: null,
      started_at: "2023-11-14T22:13:20.000Z",
      ended_at: "2023-11-14T22:13:20.120Z",
      duration_ms: 120,
      model: null,
      provider: null,
      input_tokens: null,
      output_tokens: null,
      total_tokens: null,
      cost_usd: null,
    });
    expect(span).not.toHaveProperty("tenant_slug");
    expect(span).not.toHaveProperty("tenant_slug_verified");
  });

  it("reads model, provider, tokens and cost from the emitter's attributes", () => {
    const rows = indexRows(
      [
        record("0000000000000001", {
          attributes: [
            { key: "gen_ai.request.model", value: { stringValue: "gpt-4o-mini" } },
            { key: "gen_ai.provider.name", value: { stringValue: "openai" } },
            { key: "gen_ai.usage.input_tokens", value: { intValue: "120" } },
            { key: "gen_ai.usage.output_tokens", value: { intValue: "34" } },
            { key: "digitrace.cost_usd", value: { doubleValue: 0.0021 } },
          ],
        }),
      ],
      WORKSPACE,
      RECEIVED,
      SOURCE,
    );
    expect(rows.spans[0]).toMatchObject({
      model: "gpt-4o-mini",
      provider: "openai",
      input_tokens: 120,
      output_tokens: 34,
      total_tokens: 154,
      cost_usd: 0.0021,
    });
  });

  it("prefers the source's own total_tokens over the sum", () => {
    const rows = indexRows(
      [
        record("0000000000000001", {
          attributes: [
            { key: "gen_ai.usage.input_tokens", value: { intValue: "10" } },
            { key: "gen_ai.usage.output_tokens", value: { intValue: "5" } },
            { key: "gen_ai.usage.total_tokens", value: { intValue: "99" } },
          ],
        }),
      ],
      WORKSPACE,
      RECEIVED,
      SOURCE,
    );
    expect(rows.spans[0].total_tokens).toBe(99);
  });

  it("carries the hash and length of the content, never the content", () => {
    const rows = indexRows(
      [
        record("0000000000000001", {
          attributes: [
            { key: "digi.input.sha256", value: { stringValue: "a".repeat(64) } },
            { key: "digi.input.length", value: { intValue: "42" } },
            { key: "digi.output.sha256", value: { stringValue: "b".repeat(64) } },
            { key: "digi.output.length", value: { intValue: "7" } },
            { key: "digi.input.preview", value: { stringValue: "should not be used" } },
          ],
        }),
      ],
      WORKSPACE,
      RECEIVED,
      SOURCE,
    );
    expect(rows.spans[0]).toMatchObject({
      input_hash: "a".repeat(64),
      input_length: 42,
      output_hash: "b".repeat(64),
      output_length: 7,
    });
    expect(JSON.stringify(rows.spans[0])).not.toContain("should not be used");
  });

  it("rolls spans up into one trace row with the root span's name and source", () => {
    const rows = indexRows(
      [
        record("0000000000000001", {
          name: "root",
          startTimeUnixNano: "1700000000000000000",
          endTimeUnixNano: "1700000000500000000",
        }),
        record("0000000000000002", {
          name: "child",
          parentSpanId: "0000000000000001",
          startTimeUnixNano: "1700000000100000000",
          endTimeUnixNano: "1700000000300000000",
        }),
        record("0000000000000003", {
          name: "failed-child",
          parentSpanId: "0000000000000001",
          startTimeUnixNano: "1700000000400000000",
          endTimeUnixNano: "1700000000450000000",
          status: { code: 2, message: "boom" },
        }),
      ],
      WORKSPACE,
      RECEIVED,
      SOURCE,
    );

    expect(rows.traces).toHaveLength(1);
    expect(rows.traces[0]).toMatchObject({
      workspace_id: WORKSPACE,
      source: SOURCE,
      trace_id: TRACE,
      name: "root",
      service_name: "digichat",
      started_at: "2023-11-14T22:13:20.000Z",
      ended_at: "2023-11-14T22:13:20.500Z",
      duration_ms: 500,
      span_count: 3,
      status: "STATUS_CODE_ERROR",
      status_message: "boom",
    });
    expect(rows.traces[0].attributes).toEqual({});
    expect(rows.traces[0].resource).toEqual({ "service.name": "digichat" });
  });

  it("keeps one trace row per trace id", () => {
    const other = "1af7651916cd43dd8448eb211c80319d";
    const second = record("0000000000000002");
    const rows = indexRows(
      [record("0000000000000001"), { ...second, span: { ...second.span, traceId: other } }],
      WORKSPACE,
      RECEIVED,
      SOURCE,
    );
    expect(rows.traces).toHaveLength(2);
    expect(rows.traces.map((row) => row.trace_id)).toEqual([TRACE, other].sort());
  });

  it("picks session and run ids from the correlation attributes", () => {
    const rows = indexRows(
      [
        record("0000000000000001", {
          attributes: [
            { key: "session.id", value: { stringValue: "sess-1" } },
            { key: "pipeline.run_id", value: { stringValue: "run-1" } },
          ],
        }),
      ],
      WORKSPACE,
      RECEIVED,
      SOURCE,
    );
    expect(rows.spans[0]).toMatchObject({ session_id: "sess-1", run_id: "run-1" });
    expect(rows.traces[0]).toMatchObject({ session_id: "sess-1", run_id: "run-1" });
  });

  it("is a pure function of its inputs, so a retry writes identical rows", () => {
    const once = indexRows([record("0000000000000001")], WORKSPACE, RECEIVED, SOURCE);
    const twice = indexRows([record("0000000000000001")], WORKSPACE, RECEIVED, SOURCE);
    expect(JSON.stringify(once)).toBe(JSON.stringify(twice));
  });

  it("sorts spans by trace and span id for a stable payload", () => {
    const rows = indexRows(
      [record("0000000000000002"), record("0000000000000001")],
      WORKSPACE,
      RECEIVED,
      SOURCE,
    );
    expect(rows.spans.map((row) => row.span_id)).toEqual(["0000000000000001", "0000000000000002"]);
  });
});

describe("the NOT NULL started_at fallback", () => {
  it("indexes a span with no start time at its receive time, and says so", () => {
    const rows = indexRows(
      [record("0000000000000001", { startTimeUnixNano: undefined })],
      WORKSPACE,
      RECEIVED,
      SOURCE,
    );
    expect(rows.spans[0].started_at).toBe(RECEIVED);
    expect(rows.traces[0].started_at).toBe(RECEIVED);
    // The end time the span did carry is kept; the duration is not computed
    // from a start time that is not there.
    expect(rows.spans[0].ended_at).toBe("2023-11-14T22:13:20.120Z");
    expect(rows.spans[0].duration_ms).toBeNull();
  });

  it("keeps a start time the span does carry", () => {
    expect(__internal.startedAt(record("0000000000000001"), RECEIVED)).toBe(
      "2023-11-14T22:13:20.000Z",
    );
  });
});

describe("CONFLICT_TARGETS", () => {
  it("names the unique key of each table the migration defines", () => {
    expect(CONFLICT_TARGETS).toEqual({
      traces: "workspace_id,trace_id",
      spans: "workspace_id,trace_id,span_id",
    });
  });
});
