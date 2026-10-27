import { describe, expect, it } from "vitest";
import { OtlpParseError, normalizeTraceRequest } from "./otlp-json";

const TRACE = "0af7651916cd43dd8448eb211c80319c";
const SPAN = "b7ad6b7169203331";

function request(spans: unknown[], resourceAttributes: unknown = []): unknown {
  return {
    resourceSpans: [
      {
        resource: { attributes: resourceAttributes },
        scopeSpans: [{ scope: { name: "scope.a" }, spans }],
      },
    ],
  };
}

function span(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    traceId: TRACE,
    spanId: SPAN,
    name: "GET /chat",
    ...overrides,
  };
}

describe("normalizeTraceRequest", () => {
  it("carries a well-formed span through with its resource and scope", () => {
    const result = normalizeTraceRequest(
      request([span()], [{ key: "service.name", value: { stringValue: "digichat" } }]),
    );
    expect(result.rejectedSpans).toBe(0);
    expect(result.records).toHaveLength(1);
    const [record] = result.records;
    expect(record.span.traceId).toBe(TRACE);
    expect(record.span.spanId).toBe(SPAN);
    expect(record.span.name).toBe("GET /chat");
    expect(record.scope.name).toBe("scope.a");
    expect(record.resource.attributes).toEqual([
      { key: "service.name", value: { stringValue: "digichat" } },
    ]);
  });

  it("treats a missing resourceSpans as an empty export, not an error", () => {
    expect(normalizeTraceRequest({})).toEqual({ records: [], rejectedSpans: 0 });
    expect(normalizeTraceRequest({ resourceSpans: [] })).toEqual({
      records: [],
      rejectedSpans: 0,
    });
  });

  it("keeps a decodable parent id and drops one that is not decodable", () => {
    const withParent = normalizeTraceRequest(request([span({ parentSpanId: SPAN })])).records[0];
    expect(withParent.span.parentSpanId).toBe(SPAN);

    const badParent = normalizeTraceRequest(request([span({ parentSpanId: "nope" })])).records[0];
    expect(badParent.span.parentSpanId).toBeUndefined();
  });

  it("rejects a malformed span and counts it, instead of failing the batch", () => {
    const result = normalizeTraceRequest(
      request([
        span(),
        span({ traceId: "short" }),
        span({ spanId: undefined }),
        span({ name: "" }),
        "not an object",
      ]),
    );
    expect(result.records).toHaveLength(1);
    expect(result.rejectedSpans).toBe(4);
  });

  it("refuses a malformed envelope, because the source is not speaking OTLP", () => {
    expect(() => normalizeTraceRequest(null)).toThrow(OtlpParseError);
    expect(() => normalizeTraceRequest([])).toThrow(OtlpParseError);
    expect(() => normalizeTraceRequest({ resourceSpans: "no" })).toThrow(OtlpParseError);
    expect(() => normalizeTraceRequest({ resourceSpans: [{ scopeSpans: "no" }] })).toThrow(
      OtlpParseError,
    );
    expect(() =>
      normalizeTraceRequest({
        resourceSpans: [{ scopeSpans: [{ spans: "no" }] }],
      }),
    ).toThrow(OtlpParseError);
  });

  it("drops attribute entries that are not key/value pairs", () => {
    const result = normalizeTraceRequest(
      request([
        span({
          attributes: [
            { key: "ok", value: { stringValue: "yes" } },
            { key: "no-value" },
            { value: { stringValue: "no key" } },
            "junk",
          ],
        }),
      ]),
    );
    expect(result.records[0].span.attributes).toEqual([
      { key: "ok", value: { stringValue: "yes" } },
    ]);
  });

  it("keeps events that are objects and drops the rest", () => {
    const result = normalizeTraceRequest(
      request([
        span({
          events: [
            {
              name: "exception",
              attributes: [{ key: "exception.type", value: { stringValue: "E" } }],
            },
            "junk",
          ],
        }),
      ]),
    );
    expect(result.records[0].span.events).toHaveLength(1);
    expect(result.records[0].span.events?.[0].name).toBe("exception");
  });

  it("normalises the base64 id spelling to hex", () => {
    let binary = "";
    for (let i = 0; i < TRACE.length; i += 2) {
      binary += String.fromCharCode(Number.parseInt(TRACE.slice(i, i + 2), 16));
    }
    const result = normalizeTraceRequest(request([span({ traceId: btoa(binary) })]));
    expect(result.records[0].span.traceId).toBe(TRACE);
  });
});
