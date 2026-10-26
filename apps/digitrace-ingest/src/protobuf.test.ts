import { describe, expect, it } from "vitest";
import { OtlpParseError } from "./otlp-json";
import { decodeTraceRequest, encodeTraceResponse } from "./protobuf";

/**
 * A minimal protobuf writer, in the test only.
 *
 * The Worker never encodes a request; it only reads one. Writing the fixtures by
 * hand here keeps the test independent of the decoder it is testing — a fixture
 * produced by the decoder would prove nothing.
 */
function varint(value: number | bigint): number[] {
  let v = typeof value === "bigint" ? value : BigInt(value);
  if (v < 0n) v = BigInt.asUintN(64, v);
  const out: number[] = [];
  while (v > 0x7fn) {
    out.push(Number((v & 0x7fn) | 0x80n));
    v >>= 7n;
  }
  out.push(Number(v));
  return out;
}

function tag(field: number, wire: number): number[] {
  return varint((field << 3) | wire);
}

function bytesField(field: number, value: number[] | Uint8Array): number[] {
  const body = Array.from(value);
  return [...tag(field, 2), ...varint(body.length), ...body];
}

function stringField(field: number, value: string): number[] {
  return bytesField(field, Array.from(new TextEncoder().encode(value)));
}

function varintField(field: number, value: number | bigint): number[] {
  return [...tag(field, 0), ...varint(value)];
}

function fixed64Field(field: number, value: bigint): number[] {
  const buffer = new ArrayBuffer(8);
  new DataView(buffer).setBigUint64(0, value, true);
  return [...tag(field, 1), ...Array.from(new Uint8Array(buffer))];
}

function doubleField(field: number, value: number): number[] {
  const buffer = new ArrayBuffer(8);
  new DataView(buffer).setFloat64(0, value, true);
  return [...tag(field, 1), ...Array.from(new Uint8Array(buffer))];
}

function hexBytes(hex: string): number[] {
  const out: number[] = [];
  for (let i = 0; i < hex.length; i += 2) out.push(Number.parseInt(hex.slice(i, i + 2), 16));
  return out;
}

function keyValueString(key: string, value: string): number[] {
  return [...stringField(1, key), ...bytesField(2, stringField(1, value))];
}

function keyValueInt(key: string, value: number): number[] {
  return [...stringField(1, key), ...bytesField(2, varintField(3, value))];
}

function keyValueDouble(key: string, value: number): number[] {
  return [...stringField(1, key), ...bytesField(2, doubleField(4, value))];
}

const TRACE = "0af7651916cd43dd8448eb211c80319c";
const SPAN = "b7ad6b7169203331";
const PARENT = "1122334455667788";

interface BuildSpan {
  traceId?: string;
  spanId?: string;
  parentSpanId?: string;
  name?: string;
  kind?: number;
  start?: bigint;
  end?: bigint;
  attributes?: number[][];
  events?: number[][];
  status?: number[];
  extra?: number[];
}

function buildSpan(options: BuildSpan = {}): number[] {
  const fields: number[] = [
    ...bytesField(1, hexBytes(options.traceId ?? TRACE)),
    ...bytesField(2, hexBytes(options.spanId ?? SPAN)),
    ...stringField(5, options.name ?? "GET /chat"),
    ...varintField(6, options.kind ?? 2),
    ...fixed64Field(7, options.start ?? 1_700_000_000_000_000_000n),
    ...fixed64Field(8, options.end ?? 1_700_000_000_120_000_000n),
  ];
  if (options.parentSpanId !== undefined) {
    fields.push(...bytesField(4, hexBytes(options.parentSpanId)));
  }
  for (const attribute of options.attributes ?? []) fields.push(...bytesField(9, attribute));
  for (const event of options.events ?? []) fields.push(...bytesField(11, event));
  if (options.status) fields.push(...bytesField(15, options.status));
  if (options.extra) fields.push(...options.extra);
  return fields;
}

function buildRequest(spans: number[][], resourceAttributes: number[][] = []): Uint8Array {
  const resource: number[] = [];
  for (const attribute of resourceAttributes) resource.push(...bytesField(1, attribute));

  const scopeSpans: number[] = [...bytesField(1, stringField(1, "digitrace.test"))];
  for (const span of spans) scopeSpans.push(...bytesField(2, span));

  const resourceSpans: number[] = [...bytesField(1, resource), ...bytesField(2, scopeSpans)];

  return new Uint8Array(bytesField(1, resourceSpans));
}

describe("decodeTraceRequest", () => {
  it("decodes a span into the JSON mapping's shapes", () => {
    const bytes = buildRequest(
      [
        buildSpan({
          parentSpanId: PARENT,
          attributes: [
            keyValueString("gen_ai.request.model", "gpt-4o-mini"),
            keyValueInt("gen_ai.usage.input_tokens", 42),
            keyValueDouble("digitrace.cost_usd", 0.0015),
          ],
          status: [...stringField(2, "boom"), ...varintField(3, 2)],
        }),
      ],
      [keyValueString("service.name", "digichat")],
    );

    const request = decodeTraceRequest(bytes);
    expect(request.resourceSpans).toHaveLength(1);
    const [resourceSpans] = request.resourceSpans ?? [];
    expect(resourceSpans.resource?.attributes).toEqual([
      { key: "service.name", value: { stringValue: "digichat" } },
    ]);
    const [scopeSpans] = resourceSpans.scopeSpans ?? [];
    expect(scopeSpans.scope?.name).toBe("digitrace.test");

    const [span] = scopeSpans.spans ?? [];
    expect(span.traceId).toBe(TRACE);
    expect(span.spanId).toBe(SPAN);
    expect(span.parentSpanId).toBe(PARENT);
    expect(span.name).toBe("GET /chat");
    expect(span.kind).toBe(2);
    expect(span.startTimeUnixNano).toBe("1700000000000000000");
    expect(span.endTimeUnixNano).toBe("1700000000120000000");
    expect(span.attributes).toEqual([
      { key: "gen_ai.request.model", value: { stringValue: "gpt-4o-mini" } },
      { key: "gen_ai.usage.input_tokens", value: { intValue: "42" } },
      { key: "digitrace.cost_usd", value: { doubleValue: 0.0015 } },
    ]);
    expect(span.status).toEqual({ message: "boom", code: 2 });
  });

  it("decodes a negative int64 as a negative intValue", () => {
    const bytes = buildRequest([buildSpan({ attributes: [keyValueInt("temperature_delta", -3)] })]);
    const span = decodeTraceRequest(bytes).resourceSpans?.[0].scopeSpans?.[0].spans?.[0];
    expect(span?.attributes?.[0].value.intValue).toBe("-3");
  });

  it("decodes events, including their own attributes", () => {
    const event = [
      ...fixed64Field(1, 1_700_000_000_050_000_000n),
      ...stringField(2, "exception"),
      ...bytesField(3, keyValueString("exception.type", "ValueError")),
    ];
    const bytes = buildRequest([buildSpan({ events: [event] })]);
    const span = decodeTraceRequest(bytes).resourceSpans?.[0].scopeSpans?.[0].spans?.[0];
    expect(span?.events?.[0].name).toBe("exception");
    expect(span?.events?.[0].timeUnixNano).toBe("1700000000050000000");
    expect(span?.events?.[0].attributes?.[0]).toEqual({
      key: "exception.type",
      value: { stringValue: "ValueError" },
    });
  });

  it("skips an unknown field number instead of failing the message", () => {
    const bytes = buildRequest([buildSpan({ extra: [...varintField(99, 7)] })]);
    const span = decodeTraceRequest(bytes).resourceSpans?.[0].scopeSpans?.[0].spans?.[0];
    expect(span?.name).toBe("GET /chat");
  });

  it("decodes array and kvlist attribute values", () => {
    const array = bytesField(5, [
      ...bytesField(1, stringField(1, "a")),
      ...bytesField(1, stringField(1, "b")),
    ]);
    const kvlist = bytesField(6, bytesField(1, keyValueString("k", "v")));
    const bytes = buildRequest([
      buildSpan({
        attributes: [
          [...stringField(1, "tags"), ...bytesField(2, array)],
          [...stringField(1, "meta"), ...bytesField(2, kvlist)],
        ],
      }),
    ]);
    const attributes =
      decodeTraceRequest(bytes).resourceSpans?.[0].scopeSpans?.[0].spans?.[0]?.attributes;
    expect(attributes?.[0].value.arrayValue?.values).toEqual([
      { stringValue: "a" },
      { stringValue: "b" },
    ]);
    expect(attributes?.[1].value.kvlistValue?.values).toEqual([
      { key: "k", value: { stringValue: "v" } },
    ]);
  });

  it("refuses a truncated body instead of returning half a trace", () => {
    const bytes = buildRequest([buildSpan()]);
    expect(() => decodeTraceRequest(bytes.subarray(0, bytes.length - 3))).toThrow(OtlpParseError);
  });

  it("refuses a wire type OTLP never uses", () => {
    // Wire type 3 is the deprecated start-group form: a corrupt body, not a
    // newer minor version.
    const bytes = Uint8Array.from([...tag(1, 3), 0x00]);
    expect(() => decodeTraceRequest(bytes)).toThrow(OtlpParseError);
  });

  it("decodes an empty body as an empty export", () => {
    expect(decodeTraceRequest(new Uint8Array(0))).toEqual({});
  });
});

describe("encodeTraceResponse", () => {
  it("returns an empty message for a fully successful export", () => {
    expect(encodeTraceResponse(0)).toHaveLength(0);
  });

  it("encodes partial success as ExportTraceServiceResponse", () => {
    // field 1 (partial_success), length 2, then rejected_spans = 3.
    expect(Array.from(encodeTraceResponse(3))).toEqual([0x0a, 0x02, 0x08, 0x03]);
  });

  it("carries an error message when one is given", () => {
    // field 1 (partial_success), 6 bytes: rejected_spans = 1, error_message = "no".
    const bytes = Array.from(encodeTraceResponse(1, "no"));
    expect(bytes.slice(0, 2)).toEqual([0x0a, 0x06]);
    expect(bytes.slice(2)).toEqual([0x08, 0x01, 0x12, 0x02, 0x6e, 0x6f]);
  });
});
