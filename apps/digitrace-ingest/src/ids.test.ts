import { describe, expect, it } from "vitest";
import { idBytes, spanIdHex, traceIdHex } from "./ids";

/** The base64 spelling the Collector's JSON exporter uses for a hex id. */
function base64OfHex(hex: string): string {
  let binary = "";
  for (let i = 0; i < hex.length; i += 2) {
    binary += String.fromCharCode(Number.parseInt(hex.slice(i, i + 2), 16));
  }
  return btoa(binary);
}

const TRACE_HEX = "0af7651916cd43dd8448eb211c80319c";
const SPAN_HEX = "b7ad6b7169203331";

describe("traceIdHex", () => {
  it("keeps a 32-character hex id, lowercased", () => {
    expect(traceIdHex(TRACE_HEX.toUpperCase())).toBe(TRACE_HEX);
  });

  it("decodes the base64 spelling to the same hex", () => {
    expect(traceIdHex(base64OfHex(TRACE_HEX))).toBe(TRACE_HEX);
  });

  it("accepts the URL-safe base64 alphabet", () => {
    const hex = "ffffffffffffffffffffffffffffffff";
    const standard = base64OfHex(hex).replace(/\+/g, "-").replace(/\//g, "_");
    expect(traceIdHex(standard)).toBe(hex);
  });

  it("decodes an all-zero id without a special case: reserved is not forbidden", () => {
    const zero = "0".repeat(32);
    // The decode is a shape decision, not an all-zero policy; the receiver stores
    // what the exporter sent, and OTLP reserves but does not forbid it.
    expect(traceIdHex(zero)).toBe(zero);
  });

  it("rejects a hex id of the wrong length instead of guessing", () => {
    expect(traceIdHex(TRACE_HEX.slice(0, 30))).toBeUndefined();
    expect(traceIdHex(`${TRACE_HEX}00`)).toBeUndefined();
  });

  it("rejects base64 that decodes to the wrong number of bytes", () => {
    expect(traceIdHex(base64OfHex(SPAN_HEX))).toBeUndefined();
  });

  it("rejects a non-string, an empty string and junk", () => {
    expect(traceIdHex(undefined)).toBeUndefined();
    expect(traceIdHex(42)).toBeUndefined();
    expect(traceIdHex("")).toBeUndefined();
    expect(traceIdHex("not an id!")).toBeUndefined();
  });
});

describe("spanIdHex", () => {
  it("keeps a 16-character hex id", () => {
    expect(spanIdHex(SPAN_HEX)).toBe(SPAN_HEX);
  });

  it("decodes the base64 spelling", () => {
    expect(spanIdHex(base64OfHex(SPAN_HEX))).toBe(SPAN_HEX);
  });

  it("rejects a trace-length id", () => {
    expect(spanIdHex(TRACE_HEX)).toBeUndefined();
  });
});

describe("idBytes", () => {
  it("returns the bytes behind the hex", () => {
    expect(Array.from(idBytes("0102ff"))).toEqual([1, 2, 255]);
  });
});
