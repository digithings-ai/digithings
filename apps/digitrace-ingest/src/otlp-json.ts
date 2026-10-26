/**
 * OTLP/JSON normalisation.
 *
 * Both encodings end up here: a JSON body is validated, and a protobuf body is
 * decoded into the same JSON shapes first (`protobuf.ts`). One normalisation
 * path means one archive format and one set of index columns.
 *
 * Two failure classes, deliberately different:
 *   - a malformed *envelope* throws `OtlpParseError` and the request is refused
 *     with 400, because the source is not speaking OTLP;
 *   - a malformed *span* is counted as rejected and reported through OTLP's own
 *     `partialSuccess`, because dropping the whole batch for one bad span would
 *     lose the spans that are fine. The count is in the response, so a silent
 *     loss is not possible.
 */
import { spanIdHex, traceIdHex } from "./ids";
import type {
  OtlpEvent,
  OtlpKeyValue,
  OtlpResource,
  OtlpScope,
  OtlpScopeSpans,
  OtlpSpan,
  SpanRecord,
} from "./types";

export class OtlpParseError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "OtlpParseError";
  }
}

export interface NormalizeResult {
  records: SpanRecord[];
  /** Spans present in the request but not carried forward (malformed). */
  rejectedSpans: number;
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** An attribute list as an array, ignoring anything that is not one. */
function attributeList(value: unknown): OtlpKeyValue[] | undefined {
  if (!Array.isArray(value)) return undefined;
  const out: OtlpKeyValue[] = [];
  for (const entry of value) {
    if (!isObject(entry) || typeof entry.key !== "string") continue;
    if (!isObject(entry.value)) continue;
    out.push(entry as unknown as OtlpKeyValue);
  }
  return out;
}

function resourceOf(value: unknown): OtlpResource {
  const attributes = isObject(value) ? attributeList(value.attributes) : undefined;
  return attributes ? { attributes } : {};
}

function scopeOf(value: unknown): OtlpScope {
  const scope: OtlpScope = {};
  if (!isObject(value)) return scope;
  if (typeof value.name === "string") scope.name = value.name;
  if (typeof value.version === "string") scope.version = value.version;
  const attributes = attributeList(value.attributes);
  if (attributes) scope.attributes = attributes;
  return scope;
}

function eventsOf(value: unknown): OtlpEvent[] | undefined {
  if (!Array.isArray(value)) return undefined;
  const out: OtlpEvent[] = [];
  for (const entry of value) {
    if (!isObject(entry)) continue;
    const event: OtlpEvent = {};
    if (typeof entry.name === "string") event.name = entry.name;
    if (typeof entry.timeUnixNano === "string" || typeof entry.timeUnixNano === "number") {
      event.timeUnixNano = entry.timeUnixNano;
    }
    const attributes = attributeList(entry.attributes);
    if (attributes) event.attributes = attributes;
    out.push(event);
  }
  return out;
}

/** One span, or undefined when it cannot be indexed as a span. */
function spanOf(value: Record<string, unknown>): OtlpSpan | undefined {
  const traceId = traceIdHex(value.traceId);
  const spanId = spanIdHex(value.spanId);
  if (traceId === undefined || spanId === undefined) return undefined;
  if (typeof value.name !== "string" || value.name === "") return undefined;

  const span: OtlpSpan = { ...(value as unknown as OtlpSpan), traceId, spanId };

  // A parent id that will not decode is not a reason to drop the span: it is a
  // reason not to claim a parent, so the row reports itself as a root.
  if (value.parentSpanId !== undefined && value.parentSpanId !== "") {
    const parent = spanIdHex(value.parentSpanId);
    if (parent === undefined) delete span.parentSpanId;
    else span.parentSpanId = parent;
  } else {
    delete span.parentSpanId;
  }

  const attributes = attributeList(value.attributes);
  if (attributes) span.attributes = attributes;
  const events = eventsOf(value.events);
  if (events) span.events = events;
  return span;
}

/**
 * Normalise one OTLP/JSON trace export request.
 *
 * @throws OtlpParseError when the body is not an OTLP trace export envelope.
 */
export function normalizeTraceRequest(body: unknown): NormalizeResult {
  if (!isObject(body)) {
    throw new OtlpParseError("body is not a JSON object");
  }
  const resourceSpans = body.resourceSpans;
  if (resourceSpans === undefined || resourceSpans === null) {
    // An empty request is legal OTLP: the exporter had nothing to send.
    return { records: [], rejectedSpans: 0 };
  }
  if (!Array.isArray(resourceSpans)) {
    throw new OtlpParseError("resourceSpans is not an array");
  }

  const records: SpanRecord[] = [];
  let rejectedSpans = 0;

  for (const resourceEntry of resourceSpans) {
    if (!isObject(resourceEntry)) {
      throw new OtlpParseError("resourceSpans entry is not an object");
    }
    const resource = resourceOf(resourceEntry.resource);
    const scopeSpansRaw = resourceEntry.scopeSpans;
    if (scopeSpansRaw !== undefined && scopeSpansRaw !== null && !Array.isArray(scopeSpansRaw)) {
      throw new OtlpParseError("scopeSpans is not an array");
    }

    for (const scopeEntry of (scopeSpansRaw ?? []) as unknown[]) {
      if (!isObject(scopeEntry)) {
        throw new OtlpParseError("scopeSpans entry is not an object");
      }
      const scopeSpans = scopeEntry as unknown as OtlpScopeSpans;
      const scope = scopeOf(scopeSpans.scope);
      const spans = scopeSpans.spans;
      if (spans !== undefined && spans !== null && !Array.isArray(spans)) {
        throw new OtlpParseError("spans is not an array");
      }

      for (const spanEntry of (spans ?? []) as unknown[]) {
        const span = isObject(spanEntry) ? spanOf(spanEntry) : undefined;
        if (!span) {
          rejectedSpans += 1;
          continue;
        }
        records.push({ resource, scope, span });
      }
    }
  }

  return { records, rejectedSpans };
}
