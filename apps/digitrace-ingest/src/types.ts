/**
 * Shapes this Worker reads and writes.
 *
 * The OTLP types are the subset of the OpenTelemetry trace export message the
 * ingest path actually indexes. They are written in the JSON mapping's camelCase
 * spelling, because that is the form the archive stores: a protobuf request is
 * decoded into exactly these shapes, so there is one normalisation path and one
 * archive format regardless of what the source sent.
 */

/** One queue message: one R2 object. */
export interface IngestMessage {
  /** Schema version of this message. Bump only with a consumer-side migration. */
  v: 1;
  /** Shared by every chunk of one HTTP request, so a batch is still identifiable. */
  batchId: string;
  /** 0-based index of this chunk in the request. */
  chunk: number;
  /** Number of chunks the request produced. */
  chunks: number;
  /** The tenant slug the token is allowed to write for (never the client's word alone). */
  tenant: string;
  /**
   * ADR-0036 §2: false on the static-token path. Only a digikey-signed JWT
   * carrying the claim sets it true, and that path does not exist yet.
   */
  tenantSlugVerified: boolean;
  /** The source that owns the token, from the KV record — not from the request. */
  source: string;
  /** ISO-8601 receive time. Fixes the archive object's date partition. */
  receivedAt: string;
  /** The object key under the bucket, so the consumer cannot invent a layout. */
  archiveKey: string;
  /**
   * Trace ids this message cannot carry in full, present only when one trace
   * alone exceeded the message budget and had to be split across chunks.
   *
   * `digitrace_traces` holds cross-span aggregates (`span_count`, the time
   * range, `name`, `status`), and an upsert replaces a row rather than
   * merging into it. The consumer therefore inserts the row and immediately
   * recomputes it from `digitrace_spans_index`; this list marks the traces whose
   * aggregate cannot be complete from this message alone, so a reader (and a
   * future consumer without the recompute) can tell a slice from a whole.
   */
  incompleteTraces?: string[];
  /** One span record per line (see `archiveLine` in archive.ts). */
  ndjson: string;
}

export interface Env {
  ARCHIVE: R2Bucket;
  INGEST_TOKENS: KVNamespace;
  INGEST_QUEUE: Queue<IngestMessage>;
  ANALYTICS: AnalyticsEngineDataset;
  /** D1 `digitrace`, the queryable index (migrations/0001_digitrace_index.sql). */
  INDEX_DB?: D1Database;
  /**
   * Test-only seam: the token lookup, the clock and the queue are real bindings
   * in production. Nothing here changes production behaviour when unset.
   */
  DIGITRACE_NOW?: string;
}

/** The KV record behind one ingest token. */
export interface TokenRecord {
  /** The source Worker or job that owns this token, e.g. `digitrace-digichat`. */
  source: string;
  /** The tenant slugs this token may write for. Anything else is rejected. */
  tenants: string[];
}

/** An OTLP attribute value (the JSON mapping's oneof). */
export interface OtlpAnyValue {
  stringValue?: string;
  boolValue?: boolean;
  /** int64 as a decimal string, per the JSON mapping. */
  intValue?: string | number;
  doubleValue?: number;
  arrayValue?: { values?: OtlpAnyValue[] };
  kvlistValue?: { values?: OtlpKeyValue[] };
  /** base64 of the raw bytes. */
  bytesValue?: string;
}

export interface OtlpKeyValue {
  key: string;
  value: OtlpAnyValue;
}

export interface OtlpEvent {
  timeUnixNano?: string | number;
  name?: string;
  attributes?: OtlpKeyValue[];
  droppedAttributesCount?: number;
}

export interface OtlpSpan {
  traceId: string;
  spanId: string;
  parentSpanId?: string;
  traceState?: string;
  name: string;
  /** Enum name in the JSON mapping (`SPAN_KIND_SERVER`), or the number as sent. */
  kind?: string | number;
  startTimeUnixNano?: string | number;
  endTimeUnixNano?: string | number;
  attributes?: OtlpKeyValue[];
  droppedAttributesCount?: number;
  events?: OtlpEvent[];
  droppedEventsCount?: number;
  status?: { code?: string | number; message?: string };
  flags?: number;
}

export interface OtlpScope {
  name?: string;
  version?: string;
  attributes?: OtlpKeyValue[];
}

export interface OtlpScopeSpans {
  scope?: OtlpScope;
  spans?: OtlpSpan[];
  schemaUrl?: string;
}

export interface OtlpResource {
  attributes?: OtlpKeyValue[];
  droppedAttributesCount?: number;
}

export interface OtlpResourceSpans {
  resource?: OtlpResource;
  scopeSpans?: OtlpScopeSpans[];
  schemaUrl?: string;
}

export interface OtlpTraceRequest {
  resourceSpans?: OtlpResourceSpans[];
}

/** One span, with the resource and scope it arrived under. */
export interface SpanRecord {
  resource: OtlpResource;
  scope: OtlpScope;
  span: OtlpSpan;
}

/** Everything one archive line carries. */
export interface ArchiveLine {
  tenant_slug: string;
  tenant_slug_verified: boolean;
  source: string;
  batch_id: string;
  chunk: number;
  chunks: number;
  received_at: string;
  resource: OtlpResource;
  scope: OtlpScope;
  span: OtlpSpan;
}
