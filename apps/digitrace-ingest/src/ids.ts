/**
 * Trace and span identifiers.
 *
 * OTLP defines both as byte fields, and the JSON mapping encodes bytes as
 * base64. Real exporters disagree in practice: the OpenTelemetry JS SDK and the
 * Cloudflare destinations emit the hex spelling, the Python exporter's JSON path
 * and the Collector's `json` exporter emit base64. Accepting both here is what
 * lets one ingest endpoint serve both kinds of source without a per-source mode,
 * and it is decided by the bytes, not by a header a client can set.
 */

const BASE64 = /^[A-Za-z0-9+/_-]+={0,2}$/;

/**
 * A trace id: 32 lowercase hex characters, decoded from hex or base64.
 *
 * Returns undefined rather than throwing, so one bad span does not fail a batch
 * that is otherwise fine; the caller decides what a malformed id means.
 */
export function traceIdHex(value: unknown): string | undefined {
  return idHex(value, 16);
}

/** A span id: 16 lowercase hex characters, decoded from hex or base64. */
export function spanIdHex(value: unknown): string | undefined {
  return idHex(value, 8);
}

function idHex(value: unknown, byteLength: number): string | undefined {
  if (typeof value !== "string" || value === "") return undefined;
  const hexLength = byteLength * 2;

  if (value.length === hexLength && /^[0-9a-fA-F]+$/.test(value)) {
    return value.toLowerCase();
  }
  // An all-hex string of the wrong length is a malformed id, not base64: base64
  // of 16 bytes is 22 or 24 characters, so this cannot shadow a valid one.
  if (/^[0-9a-fA-F]*$/.test(value)) return undefined;
  if (!BASE64.test(value)) return undefined;

  let binary: string;
  try {
    binary = atob(value.replace(/-/g, "+").replace(/_/g, "/"));
  } catch {
    return undefined;
  }
  if (binary.length !== byteLength) return undefined;
  let hex = "";
  for (let i = 0; i < binary.length; i += 1) {
    hex += binary.charCodeAt(i).toString(16).padStart(2, "0");
  }
  return hex;
}

/** The raw bytes behind a trace or span id: 16 or 8 bytes, for sampling. */
export function idBytes(hex: string): Uint8Array {
  const out = new Uint8Array(hex.length / 2);
  for (let i = 0; i < out.length; i += 1) {
    out[i] = Number.parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  }
  return out;
}
