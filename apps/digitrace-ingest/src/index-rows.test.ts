import { describe, expect, it } from "vitest";
import { CONFLICT_TARGETS, indexRows, isoFromNanos } from "./index-rows";
import type { SpanRecord } from "./types";

const TRACE = "0af7651916cd43dd8448eb211c80319c";
const WORKSPACE = "11111111-2222-3333-4444-555555555555";
const RECEIVED = "2026-10-26T12:00:00.000Z";

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
    expect(indexRows([], WORKSPACE, RECEIVED)).toEqual({ spans: [], traces: [], sessions: [] });
  });

  it("writes one span row per span, with the workspace and no tenant slug", () => {
    const rows = indexRows([record("b7ad6b7169203331")], WORKSPACE, RECEIVED);
    expect(rows.spans).toHaveLength(1);
    const [span] = rows.spans;
    expect(span).toMatchObject({
      workspace_id: WORKSPACE,
      trace_id: TRACE,
      span_id: "b7ad6b7169203331",
      parent_span_id: null,
      name: "GET /chat",
      kind: "SPAN_KIND_SERVER",
      status_code: "STATUS_CODE_UNSET",
      status_message: null,
      started_at: "2023-11-14T22:13:20.000Z",
      ended_at: "2023-11-14T22:13:20.120Z",
      duration_ms: 120,
      service_name: "digichat",
      scope_name: "digitrace.test",
      model: null,
      input_tokens: null,
      output_tokens: null,
      received_at: RECEIVED,
    });
    expect(span).not.toHaveProperty("tenant_slug");
    expect(span).not.toHaveProperty("tenant_slug_verified");
  });

  it("reads model and token usage from the gen_ai attributes", () => {
    const rows = indexRows(
      [
        record("0000000000000001", {
          attributes: [
            { key: "gen_ai.request.model", value: { stringValue: "gpt-4o-mini" } },
            { key: "gen_ai.usage.input_tokens", value: { intValue: "120" } },
            { key: "gen_ai.usage.output_tokens", value: { intValue: "34" } },
          ],
        }),
      ],
      WORKSPACE,
      RECEIVED,
    );
    expect(rows.spans[0]).toMatchObject({
      model: "gpt-4o-mini",
      input_tokens: 120,
      output_tokens: 34,
    });
    expect(rows.traces[0]).toMatchObject({
      model: "gpt-4o-mini",
      input_tokens: 120,
      output_tokens: 34,
    });
  });

  it("rolls spans up into one trace row with the root span's name", () => {
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
    );

    expect(rows.traces).toHaveLength(1);
    expect(rows.traces[0]).toMatchObject({
      workspace_id: WORKSPACE,
      trace_id: TRACE,
      root_span_name: "root",
      root_service_name: "digichat",
      started_at: "2023-11-14T22:13:20.000Z",
      ended_at: "2023-11-14T22:13:20.500Z",
      duration_ms: 500,
      span_count: 3,
      error_count: 1,
      status_code: "STATUS_CODE_ERROR",
    });
  });

  it("keeps one trace row per trace id", () => {
    const other = "1af7651916cd43dd8448eb211c80319d";
    const rows = indexRows(
      [
        record("0000000000000001"),
        {
          ...record("0000000000000002"),
          span: { ...record("0000000000000002").span, traceId: other },
        },
      ],
      WORKSPACE,
      RECEIVED,
    );
    expect(rows.traces).toHaveLength(2);
    expect(rows.traces.map((row) => row.trace_id)).toEqual([TRACE, other].sort());
  });

  it("derives session rows from the session.id attribute", () => {
    const rows = indexRows(
      [
        record("0000000000000001", {
          startTimeUnixNano: "1700000000000000000",
          attributes: [{ key: "session.id", value: { stringValue: "sess-1" } }],
        }),
        record("0000000000000002", {
          startTimeUnixNano: "1700000001000000000",
          endTimeUnixNano: "1700000002000000000",
          attributes: [{ key: "session.id", value: { stringValue: "sess-1" } }],
        }),
      ],
      WORKSPACE,
      RECEIVED,
    );
    expect(rows.sessions).toHaveLength(1);
    expect(rows.sessions[0]).toMatchObject({
      workspace_id: WORKSPACE,
      session_id: "sess-1",
      first_seen_at: "2023-11-14T22:13:20.000Z",
      last_seen_at: "2023-11-14T22:13:22.000Z",
      received_at: RECEIVED,
    });
    expect(rows.traces[0].session_id).toBe("sess-1");
  });

  it("is a pure function of its inputs, so a retry writes identical rows", () => {
    const once = indexRows([record("0000000000000001")], WORKSPACE, RECEIVED);
    const twice = indexRows([record("0000000000000001")], WORKSPACE, RECEIVED);
    expect(JSON.stringify(once)).toBe(JSON.stringify(twice));
  });

  it("sorts spans by trace and span id for a stable payload", () => {
    const rows = indexRows(
      [record("0000000000000002"), record("0000000000000001")],
      WORKSPACE,
      RECEIVED,
    );
    expect(rows.spans.map((row) => row.span_id)).toEqual(["0000000000000001", "0000000000000002"]);
  });
});

describe("CONFLICT_TARGETS", () => {
  it("names the natural key of each index table", () => {
    expect(CONFLICT_TARGETS).toEqual({
      traces: "workspace_id,trace_id",
      spans: "workspace_id,trace_id,span_id",
      sessions: "workspace_id,session_id",
    });
  });
});
