/**
 * OTLP protobuf, decoded.
 *
 * Why hand-rolled: the ingest path needs the trace export message and nothing
 * else, and ADR-0036 keeps a Worker's dependency list to what it already has. A
 * general protobuf runtime plus the generated OTLP descriptors is a large
 * surface to carry for two message grammars, so this module implements exactly
 * the subset below, with the unknown-field rule the spec requires (skip it, do
 * not fail) so a future OTLP minor version cannot break ingest.
 *
 * Decoded only, and deliberately so: an unknown *wire type* is a corrupt body
 * and is refused, while an unknown *field number* is skipped.
 *
 * The output shapes are the JSON mapping's, so `normalizeTraceRequest` is the
 * only normalisation path.
 */
import { OtlpParseError } from "./otlp-json";
import type {
  OtlpAnyValue,
  OtlpEvent,
  OtlpKeyValue,
  OtlpResource,
  OtlpResourceSpans,
  OtlpScope,
  OtlpScopeSpans,
  OtlpSpan,
  OtlpTraceRequest,
} from "./types";

const utf8 = new TextDecoder();

const WIRE_VARINT = 0;
const WIRE_FIXED64 = 1;
const WIRE_LENGTH = 2;
const WIRE_FIXED32 = 5;

/**
 * How deep an attribute value may nest before the body is refused.
 *
 * `arrayValue` and `kvlistValue` recurse, and a few hundred bytes of crafted
 * protobuf nesting is enough to exhaust the stack — a 500 rather than a parse
 * error. The real emitters nest two levels at most; 32 is far above any real
 * payload and far below the stack.
 */
const MAX_ATTRIBUTE_DEPTH = 32;

interface WireField {
  number: number;
  wire: number;
  varint?: bigint;
  bytes?: Uint8Array;
  fixed32?: number;
  /** The 8 raw bytes of a fixed64, kept so a double can be read off them. */
  fixed64Bytes?: Uint8Array;
}

function readVarint(buffer: Uint8Array, offset: number, end: number): [bigint, number] {
  let shift = 0n;
  let value = 0n;
  let pos = offset;
  while (pos < end) {
    const byte = buffer[pos];
    pos += 1;
    value |= BigInt(byte & 0x7f) << shift;
    if ((byte & 0x80) === 0) return [value, pos];
    shift += 7n;
    if (shift > 63n) throw new OtlpParseError("protobuf varint is longer than 10 bytes");
  }
  throw new OtlpParseError("protobuf varint is truncated");
}

/** Every field of one message, in wire order. */
function readFields(buffer: Uint8Array): WireField[] {
  const fields: WireField[] = [];
  let pos = 0;
  const end = buffer.length;
  while (pos < end) {
    const [rawTag, afterTag] = readVarint(buffer, pos, end);
    pos = afterTag;
    const tag = Number(rawTag);
    const number = tag >>> 3;
    const wire = tag & 0x7;
    if (number <= 0 || number > 0x1f_ffff) {
      throw new OtlpParseError(`protobuf field number ${number} is out of range`);
    }

    if (wire === WIRE_VARINT) {
      const [value, after] = readVarint(buffer, pos, end);
      pos = after;
      fields.push({ number, wire, varint: value });
    } else if (wire === WIRE_FIXED64) {
      if (pos + 8 > end) throw new OtlpParseError("protobuf fixed64 is truncated");
      fields.push({ number, wire, fixed64Bytes: buffer.subarray(pos, pos + 8) });
      pos += 8;
    } else if (wire === WIRE_LENGTH) {
      const [rawLength, after] = readVarint(buffer, pos, end);
      pos = after;
      if (rawLength > BigInt(end - pos)) {
        throw new OtlpParseError("protobuf length-delimited field runs past the end of the body");
      }
      const length = Number(rawLength);
      fields.push({ number, wire, bytes: buffer.subarray(pos, pos + length) });
      pos += length;
    } else if (wire === WIRE_FIXED32) {
      if (pos + 4 > end) throw new OtlpParseError("protobuf fixed32 is truncated");
      const view = new DataView(buffer.buffer, buffer.byteOffset + pos, 4);
      pos += 4;
      fields.push({ number, wire, fixed32: view.getUint32(0, true) });
    } else {
      throw new OtlpParseError(`protobuf wire type ${wire} is not supported`);
    }
  }
  return fields;
}

function text(bytes: Uint8Array): string {
  return utf8.decode(bytes);
}

function hex(bytes: Uint8Array): string {
  let out = "";
  for (const byte of bytes) out += byte.toString(16).padStart(2, "0");
  return out;
}

/** A `fixed64` field as an unsigned decimal string (every timestamp in OTLP). */
function fixed64Int(bytes: Uint8Array | undefined): string | undefined {
  if (!bytes || bytes.length !== 8) return undefined;
  return new DataView(bytes.buffer, bytes.byteOffset, 8).getBigUint64(0, true).toString();
}

/** A `fixed64` field read as an IEEE-754 double (`AnyValue.double_value`). */
function fixed64Double(bytes: Uint8Array | undefined): number | undefined {
  if (!bytes || bytes.length !== 8) return undefined;
  return new DataView(bytes.buffer, bytes.byteOffset, 8).getFloat64(0, true);
}

function base64(bytes: Uint8Array): string {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary);
}

/** int64 varints are two's complement, so a negative int arrives as a huge value. */
function int64(value: bigint): string {
  return BigInt.asIntN(64, value).toString();
}

function anyValue(bytes: Uint8Array, depth = 0): OtlpAnyValue {
  if (depth > MAX_ATTRIBUTE_DEPTH) {
    throw new OtlpParseError("attribute value nest is deeper than 32 levels");
  }
  const value: OtlpAnyValue = {};
  for (const field of readFields(bytes)) {
    if (field.number === 1 && field.bytes) value.stringValue = text(field.bytes);
    else if (field.number === 2 && field.varint !== undefined)
      value.boolValue = field.varint !== 0n;
    else if (field.number === 3 && field.varint !== undefined) value.intValue = int64(field.varint);
    else if (field.number === 4 && field.fixed64Bytes) {
      value.doubleValue = fixed64Double(field.fixed64Bytes);
    } else if (field.number === 5 && field.bytes) {
      value.arrayValue = { values: repeated(field.bytes, anyValue, depth + 1) };
    } else if (field.number === 6 && field.bytes) {
      value.kvlistValue = { values: repeated(field.bytes, keyValue, depth + 1) };
    } else if (field.number === 7 && field.bytes) {
      value.bytesValue = base64(field.bytes);
    }
  }
  return value;
}

/** The elements of a `repeated` field that is wrapped in its own message. */
function repeated<T>(
  bytes: Uint8Array,
  decode: (input: Uint8Array, depth: number) => T,
  depth: number,
): T[] {
  return readFields(bytes)
    .filter((field) => field.number === 1 && field.bytes !== undefined)
    .map((field) => decode(field.bytes as Uint8Array, depth));
}

/**
 * Append one element of a `repeated KeyValue` field.
 *
 * A repeated field is not wrapped in a message: each occurrence on the wire is
 * one element. So an attribute is one `keyValue(...)` call, not `repeated` over
 * a list — reading it as a list would parse the key's text as a field tag.
 */
function appendAttribute(list: OtlpKeyValue[] | undefined, bytes: Uint8Array): OtlpKeyValue[] {
  const out = list ?? [];
  out.push(keyValue(bytes));
  return out;
}

function keyValue(bytes: Uint8Array, depth = 0): OtlpKeyValue {
  let key = "";
  let value: OtlpAnyValue = {};
  for (const field of readFields(bytes)) {
    if (field.number === 1 && field.bytes) key = text(field.bytes);
    else if (field.number === 2 && field.bytes) value = anyValue(field.bytes, depth + 1);
  }
  return { key, value };
}

function event(bytes: Uint8Array): OtlpEvent {
  const out: OtlpEvent = {};
  for (const field of readFields(bytes)) {
    if (field.number === 1) out.timeUnixNano = fixed64Int(field.fixed64Bytes);
    else if (field.number === 2 && field.bytes) out.name = text(field.bytes);
    else if (field.number === 3 && field.bytes) {
      out.attributes = appendAttribute(out.attributes, field.bytes);
    } else if (field.number === 4 && field.varint !== undefined) {
      out.droppedAttributesCount = Number(field.varint);
    }
  }
  return out;
}

function status(bytes: Uint8Array): OtlpSpan["status"] {
  const out: NonNullable<OtlpSpan["status"]> = {};
  for (const field of readFields(bytes)) {
    if (field.number === 2 && field.bytes) out.message = text(field.bytes);
    else if (field.number === 3 && field.varint !== undefined) out.code = Number(field.varint);
  }
  return out;
}

function span(bytes: Uint8Array): OtlpSpan {
  const out: OtlpSpan = { traceId: "", spanId: "", name: "" };
  for (const field of readFields(bytes)) {
    switch (field.number) {
      case 1:
        if (field.bytes) out.traceId = hex(field.bytes);
        break;
      case 2:
        if (field.bytes) out.spanId = hex(field.bytes);
        break;
      case 3:
        if (field.bytes) out.traceState = text(field.bytes);
        break;
      case 4:
        if (field.bytes) out.parentSpanId = hex(field.bytes);
        break;
      case 5:
        if (field.bytes) out.name = text(field.bytes);
        break;
      case 6:
        if (field.varint !== undefined) out.kind = Number(field.varint);
        break;
      case 7:
        out.startTimeUnixNano = fixed64Int(field.fixed64Bytes);
        break;
      case 8:
        out.endTimeUnixNano = fixed64Int(field.fixed64Bytes);
        break;
      case 9:
        if (field.bytes) out.attributes = appendAttribute(out.attributes, field.bytes);
        break;
      case 10:
        if (field.varint !== undefined) out.droppedAttributesCount = Number(field.varint);
        break;
      case 11:
        if (field.bytes) (out.events ??= []).push(event(field.bytes));
        break;
      case 12:
        if (field.varint !== undefined) out.droppedEventsCount = Number(field.varint);
        break;
      case 15:
        if (field.bytes) out.status = status(field.bytes);
        break;
      case 16:
        if (field.varint !== undefined) out.flags = Number(field.varint);
        break;
      default:
        break;
    }
  }
  return out;
}

function scope(bytes: Uint8Array): OtlpScope {
  const out: OtlpScope = {};
  for (const field of readFields(bytes)) {
    if (field.number === 1 && field.bytes) out.name = text(field.bytes);
    else if (field.number === 2 && field.bytes) out.version = text(field.bytes);
    else if (field.number === 3 && field.bytes) {
      out.attributes = appendAttribute(out.attributes, field.bytes);
    }
  }
  return out;
}

function resource(bytes: Uint8Array): OtlpResource {
  const out: OtlpResource = {};
  for (const field of readFields(bytes)) {
    if (field.number === 1 && field.bytes) {
      out.attributes = appendAttribute(out.attributes, field.bytes);
    } else if (field.number === 2 && field.varint !== undefined) {
      out.droppedAttributesCount = Number(field.varint);
    }
  }
  return out;
}

function scopeSpans(bytes: Uint8Array): OtlpScopeSpans {
  const out: OtlpScopeSpans = {};
  for (const field of readFields(bytes)) {
    if (field.number === 1 && field.bytes) out.scope = scope(field.bytes);
    else if (field.number === 2 && field.bytes) (out.spans ??= []).push(span(field.bytes));
    else if (field.number === 3 && field.bytes) out.schemaUrl = text(field.bytes);
  }
  return out;
}

function resourceSpans(bytes: Uint8Array): OtlpResourceSpans {
  const out: OtlpResourceSpans = {};
  for (const field of readFields(bytes)) {
    if (field.number === 1 && field.bytes) out.resource = resource(field.bytes);
    else if (field.number === 2 && field.bytes)
      (out.scopeSpans ??= []).push(scopeSpans(field.bytes));
    else if (field.number === 3 && field.bytes) out.schemaUrl = text(field.bytes);
  }
  return out;
}

/**
 * Decode an `ExportTraceServiceRequest`.
 *
 * @throws OtlpParseError when the bytes are not a protobuf message of that shape.
 */
export function decodeTraceRequest(bytes: Uint8Array): OtlpTraceRequest {
  const request: OtlpTraceRequest = {};
  for (const field of readFields(bytes)) {
    if (field.number === 1 && field.bytes) {
      (request.resourceSpans ??= []).push(resourceSpans(field.bytes));
    }
  }
  return request;
}

// ── response encoding ───────────────────────────────────────────────────────
// An OTLP/HTTP client decodes the response in the encoding it sent. A protobuf
// source that receives JSON reads a decode failure, so the partial-success body
// is encoded in protobuf for that source.

function writeVarint(out: number[], value: bigint): void {
  let v = value;
  if (v < 0n) v = BigInt.asUintN(64, v);
  while (v > 0x7fn) {
    out.push(Number((v & 0x7fn) | 0x80n));
    v >>= 7n;
  }
  out.push(Number(v));
}

function writeTag(out: number[], field: number, wire: number): void {
  writeVarint(out, BigInt((field << 3) | wire));
}

/**
 * `ExportTraceServiceResponse` with an optional `partialSuccess`.
 *
 * A clean request returns an empty message, which is what the spec means by a
 * fully successful export.
 */
export function encodeTraceResponse(rejectedSpans: number, errorMessage = ""): Uint8Array {
  if (rejectedSpans <= 0 && errorMessage === "") return new Uint8Array(0);

  const partial: number[] = [];
  if (rejectedSpans > 0) {
    writeTag(partial, 1, WIRE_VARINT);
    writeVarint(partial, BigInt(rejectedSpans));
  }
  if (errorMessage !== "") {
    const encoded = new TextEncoder().encode(errorMessage);
    writeTag(partial, 2, WIRE_LENGTH);
    writeVarint(partial, BigInt(encoded.length));
    partial.push(...encoded);
  }

  const out: number[] = [];
  writeTag(out, 1, WIRE_LENGTH);
  writeVarint(out, BigInt(partial.length));
  out.push(...partial);
  return new Uint8Array(out);
}
