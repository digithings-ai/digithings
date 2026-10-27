/**
 * The Supabase index rows.
 *
 * The archive is the system of record; this is the queryable window over it
 * (ADR-0036 §3). Every row is a pure function of the queue message plus the
 * resolved `workspace_id`, so a retried message rewrites identical rows and the
 * upserts in `consumer.ts` are idempotent — no clock, no counter, no "now".
 *
 * The column names below are the schema DIG-2658 ships in
 * `digiquant/supabase/migrations/prod/144_digitrace_index.sql`, not an
 * independent guess: a name that does not exist there is a runtime 400 on the
 * first real batch, which no type can catch.
 *
 * Two deliberate omissions:
 *   - `tenant_slug` and `tenant_slug_verified` are nullable in that schema, and
 *     ADR-0036 §5 makes them edge values on the archived line rather than index
 *     columns. They stay unset here; the index's one tenancy column is
 *     `workspace_id`.
 *   - `digitrace_sessions` is not written by this consumer. Its `trace_count`,
 *     `span_count`, `total_tokens` and `total_cost_usd` are cross-batch
 *     aggregates, and PostgREST's upsert can only *replace* them: a second batch
 *     would overwrite a larger count with a smaller one. Writing them from a
 *     REST upsert would produce numbers that silently shrink, so the ingest path
 *     leaves the table alone; the migration and the dashboard leaf own how it is
 *     materialised.
 *   - `digitrace_scores` is not written here either. ADR-0036 §4/§8 put that
 *     write-back in MLflow.
 *
 * `digitrace_traces` is the other cross-batch aggregate. The row these
 * functions build is the one this message can see, and `consumer.ts` treats it
 * as the insert payload: after the spans are written it calls
 * `refresh_digitrace_trace`, which recomputes `span_count`, the time range, the
 * root name and the error status over **every** span of the trace. The row is
 * therefore correct even when `chunkSpans` had to split a trace (the ids in
 * `incompleteTraces`) or when the trace arrived across several OTLP requests.
 */
import {
  attributesToObject,
  COST_KEYS,
  durationMs,
  INPUT_HASH_KEYS,
  INPUT_LENGTH_KEYS,
  INPUT_TOKEN_KEYS,
  indexableAttributes,
  isErrorSpan,
  kindName,
  MODEL_KEYS,
  nanos,
  OUTPUT_HASH_KEYS,
  OUTPUT_LENGTH_KEYS,
  OUTPUT_TOKEN_KEYS,
  OUTPUT_TOTAL_KEYS,
  pick,
  pickNumber,
  PROVIDER_KEYS,
  RUN_KEYS,
  SERVICE_NAME_KEYS,
  SESSION_KEYS,
  statusName,
} from "./attributes";
import type { SpanRecord } from "./types";

export type Row = Record<string, unknown>;

export interface IndexRows {
  spans: Row[];
  traces: Row[];
}

/** An ISO-8601 timestamp from OTLP nanoseconds, or null. */
export function isoFromNanos(value: string | number | undefined): string | null {
  const n = nanos(value);
  if (n === undefined) return null;
  const millis = Number(n / 1_000_000n);
  if (!Number.isFinite(millis)) return null;
  const date = new Date(millis);
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
}

/** Every attribute the span carries, resource first so the span's own value wins. */
function attributesOf(record: SpanRecord): Record<string, string> {
  return {
    ...attributesToObject(record.resource.attributes),
    ...attributesToObject(record.span.attributes),
  };
}

/**
 * `started_at` is `NOT NULL` in the schema.
 *
 * A span without a start time is indexed at its receive time rather than
 * dropped: the archive keeps the untouched record, and the receive time is a
 * value we actually know, not an invented one.
 */
function startedAt(record: SpanRecord, receivedAt: string): string {
  return isoFromNanos(record.span.startTimeUnixNano) ?? receivedAt;
}

/** `total_tokens`: the source's own total, else the sum of the two halves. */
function totalTokens(merged: Record<string, string>): number | null {
  const declared = pickNumber(merged, OUTPUT_TOTAL_KEYS);
  if (declared !== undefined) return declared;
  const input = pickNumber(merged, INPUT_TOKEN_KEYS);
  const output = pickNumber(merged, OUTPUT_TOKEN_KEYS);
  if (input === undefined && output === undefined) return null;
  return (input ?? 0) + (output ?? 0);
}

/** The integer an attribute holds, or null. */
function intAttribute(merged: Record<string, string>, keys: string[]): number | null {
  const value = pickNumber(merged, keys);
  return value === undefined ? null : Math.trunc(value);
}

/** One `digitrace_spans_index` row. */
function spanRow(record: SpanRecord, workspaceId: string, receivedAt: string): Row {
  const merged = attributesOf(record);
  return {
    workspace_id: workspaceId,
    trace_id: record.span.traceId,
    span_id: record.span.spanId,
    parent_span_id: record.span.parentSpanId ?? null,
    name: record.span.name,
    kind: kindName(record.span),
    started_at: startedAt(record, receivedAt),
    ended_at: isoFromNanos(record.span.endTimeUnixNano),
    duration_ms: durationMs(record.span.startTimeUnixNano, record.span.endTimeUnixNano) ?? null,
    status: statusName(record.span),
    status_message: record.span.status?.message ?? null,
    session_id: pick(merged, SESSION_KEYS) ?? null,
    run_id: pick(merged, RUN_KEYS) ?? null,
    model: pick(merged, MODEL_KEYS) ?? null,
    provider: pick(merged, PROVIDER_KEYS) ?? null,
    input_tokens: intAttribute(merged, INPUT_TOKEN_KEYS),
    output_tokens: intAttribute(merged, OUTPUT_TOKEN_KEYS),
    total_tokens: totalTokens(merged),
    cost_usd: pickNumber(merged, COST_KEYS) ?? null,
    // Hash and length only; the content itself never leaves the source
    // (ADR-0036 §7, emitted by DIG-2656).
    input_hash: pick(merged, INPUT_HASH_KEYS) ?? null,
    input_length: intAttribute(merged, INPUT_LENGTH_KEYS),
    output_hash: pick(merged, OUTPUT_HASH_KEYS) ?? null,
    output_length: intAttribute(merged, OUTPUT_LENGTH_KEYS),
    // Allowlisted keys only: the archive keeps everything, the index keeps what
    // the schema says it may search (migration 144, ADR-0036 §7).
    attributes: indexableAttributes(record.span.attributes),
  };
}

interface TraceAccumulator {
  traceId: string;
  records: SpanRecord[];
  startedAt: string | null;
  endedAt: string | null;
  startedMillis: number;
  endedMillis: number;
}

/** `NOT NULL`, so it falls back to the receive time like a span row does. */
function firstStartedAt(accumulator: TraceAccumulator, receivedAt: string): string {
  return accumulator.startedAt ?? receivedAt;
}

/** The status message of the first failed span of a trace, if any. */
function failedStatusMessage(accumulator: TraceAccumulator): string | undefined {
  return accumulator.records.find((record) => isErrorSpan(record.span))?.span.status?.message;
}

/** One `digitrace_traces` row per trace id in the batch. */
function traceRow(
  accumulator: TraceAccumulator,
  source: string,
  workspaceId: string,
  receivedAt: string,
): Row {
  const root =
    accumulator.records.find((record) => record.span.parentSpanId === undefined) ??
    accumulator.records[0];
  const rootAttributes = indexableAttributes(root.span.attributes);
  const rootResource = indexableAttributes(root.resource.attributes);
  const errorCount = accumulator.records.filter((record) => isErrorSpan(record.span)).length;
  const sessionId =
    accumulator.records
      .map((record) => pick(attributesOf(record), SESSION_KEYS))
      .find((value) => value !== undefined) ?? null;
  const runId =
    accumulator.records
      .map((record) => pick(attributesOf(record), RUN_KEYS))
      .find((value) => value !== undefined) ?? null;

  return {
    workspace_id: workspaceId,
    // `source` is NOT NULL: it is the token's source, never the client's word.
    source,
    trace_id: accumulator.traceId,
    name: root.span.name,
    service_name: pick(rootResource, SERVICE_NAME_KEYS) ?? null,
    started_at: firstStartedAt(accumulator, receivedAt),
    ended_at: accumulator.endedAt,
    duration_ms:
      Number.isFinite(accumulator.startedMillis) && Number.isFinite(accumulator.endedMillis)
        ? Math.max(0, accumulator.endedMillis - accumulator.startedMillis)
        : null,
    status: errorCount > 0 ? "STATUS_CODE_ERROR" : statusName(root.span),
    // The message of the first failed span, because that is the failure the
    // trace row is reporting; the root's own message is usually absent.
    status_message:
      errorCount > 0
        ? (failedStatusMessage(accumulator) ?? null)
        : (root.span.status?.message ?? null),
    session_id: sessionId,
    run_id: runId,
    attributes: rootAttributes,
    resource: rootResource,
    span_count: accumulator.records.length,
  };
}

/** The index rows for one queue message. */
export function indexRows(
  records: SpanRecord[],
  workspaceId: string,
  receivedAt: string,
  source: string,
): IndexRows {
  if (records.length === 0) return { spans: [], traces: [] };

  const spans = records.map((record) => spanRow(record, workspaceId, receivedAt));

  const tracesById = new Map<string, TraceAccumulator>();
  for (const record of records) {
    const traceId = record.span.traceId;
    let accumulator = tracesById.get(traceId);
    if (!accumulator) {
      accumulator = {
        traceId,
        records: [],
        startedAt: null,
        endedAt: null,
        startedMillis: Number.POSITIVE_INFINITY,
        endedMillis: Number.NEGATIVE_INFINITY,
      };
      tracesById.set(traceId, accumulator);
    }
    accumulator.records.push(record);
    const start = nanos(record.span.startTimeUnixNano);
    const end = nanos(record.span.endTimeUnixNano) ?? start;
    if (start !== undefined) {
      const millis = Number(start / 1_000_000n);
      if (millis < accumulator.startedMillis) {
        accumulator.startedMillis = millis;
        accumulator.startedAt = isoFromNanos(record.span.startTimeUnixNano);
      }
    }
    if (end !== undefined) {
      const millis = Number(end / 1_000_000n);
      if (millis > accumulator.endedMillis) {
        accumulator.endedMillis = millis;
        accumulator.endedAt = isoFromNanos(
          record.span.endTimeUnixNano ?? record.span.startTimeUnixNano,
        );
      }
    }
  }

  const traces = [...tracesById.values()]
    .sort((a, b) => a.traceId.localeCompare(b.traceId))
    .map((accumulator) => traceRow(accumulator, source, workspaceId, receivedAt));

  // A stable order makes a batch idempotent in its PostgREST payload, which is
  // what an upsert with `merge-duplicates` expects on a retry.
  spans.sort((a, b) =>
    `${String(a.trace_id)}/${String(a.span_id)}`.localeCompare(
      `${String(b.trace_id)}/${String(b.span_id)}`,
    ),
  );

  return { spans, traces };
}

/** The conflict targets, named once so the migration and the consumer agree. */
export const CONFLICT_TARGETS = {
  traces: "workspace_id,trace_id",
  spans: "workspace_id,trace_id,span_id",
} as const;

/** Kept exported so a test can pin the two fallback rules directly. */
export const __internal = { startedAt, totalTokens };
