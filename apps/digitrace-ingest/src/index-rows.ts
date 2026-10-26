/**
 * The Supabase index rows.
 *
 * The archive is the system of record; this is the queryable window over it
 * (ADR-0036 §3). Every row is a pure function of the queue message plus the
 * resolved `workspace_id`, so a retried message rewrites identical rows and the
 * upserts in `consumer.ts` are idempotent — no clock, no counter, no "now".
 *
 * `tenant_slug` is deliberately absent: ADR-0036 §5 makes it an edge value that
 * lives on the archived line, and the index's one tenancy column is
 * `workspace_id`.
 *
 * `digitrace_scores` is not written here. Scores are written back from MLflow
 * through the service role (ADR-0036 §4 and §8), not by the ingest path.
 */
import {
  attributesToObject,
  durationMs,
  INPUT_TOKEN_KEYS,
  isErrorSpan,
  kindName,
  MODEL_KEYS,
  nanos,
  OUTPUT_TOKEN_KEYS,
  pick,
  pickNumber,
  SERVICE_NAME_KEYS,
  SESSION_KEYS,
  statusName,
} from "./attributes";
import type { SpanRecord } from "./types";

export type Row = Record<string, unknown>;

export interface IndexRows {
  spans: Row[];
  traces: Row[];
  sessions: Row[];
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

/** One `digitrace_spans_index` row. */
function spanRow(record: SpanRecord, workspaceId: string, receivedAt: string): Row {
  const merged = {
    ...attributesToObject(record.resource.attributes),
    ...attributesToObject(record.span.attributes),
  };
  return {
    workspace_id: workspaceId,
    trace_id: record.span.traceId,
    span_id: record.span.spanId,
    parent_span_id: record.span.parentSpanId ?? null,
    name: record.span.name,
    kind: kindName(record.span),
    status_code: statusName(record.span),
    status_message: record.span.status?.message ?? null,
    started_at: isoFromNanos(record.span.startTimeUnixNano),
    ended_at: isoFromNanos(record.span.endTimeUnixNano),
    duration_ms: durationMs(record.span.startTimeUnixNano, record.span.endTimeUnixNano) ?? null,
    service_name: pick(attributesToObject(record.resource.attributes), SERVICE_NAME_KEYS) ?? null,
    scope_name: record.scope.name ?? null,
    model: pick(merged, MODEL_KEYS) ?? null,
    input_tokens: pickNumber(merged, INPUT_TOKEN_KEYS) ?? null,
    output_tokens: pickNumber(merged, OUTPUT_TOKEN_KEYS) ?? null,
    attributes: attributesToObject(record.span.attributes),
    events: record.span.events ?? [],
    received_at: receivedAt,
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

/** One `digitrace_traces` row per trace in the batch. */
function traceRow(accumulator: TraceAccumulator, workspaceId: string, receivedAt: string): Row {
  const root = accumulator.records.find((record) => record.span.parentSpanId === undefined);
  const first = root ?? accumulator.records[0];
  const errorCount = accumulator.records.filter((record) => isErrorSpan(record.span)).length;
  const merged = {
    ...attributesToObject(first.resource.attributes),
    ...attributesToObject(first.span.attributes),
  };
  const sessionId =
    accumulator.records
      .map((record) =>
        pick(
          {
            ...attributesToObject(record.resource.attributes),
            ...attributesToObject(record.span.attributes),
          },
          SESSION_KEYS,
        ),
      )
      .find((value) => value !== undefined) ?? null;
  const sum = (keys: string[]): number =>
    accumulator.records.reduce(
      (total, record) =>
        total +
        (pickNumber(
          {
            ...attributesToObject(record.resource.attributes),
            ...attributesToObject(record.span.attributes),
          },
          keys,
        ) ?? 0),
      0,
    );

  return {
    workspace_id: workspaceId,
    trace_id: accumulator.traceId,
    root_span_name: first.span.name,
    root_service_name:
      pick(attributesToObject(first.resource.attributes), SERVICE_NAME_KEYS) ?? null,
    started_at: accumulator.startedAt,
    ended_at: accumulator.endedAt,
    duration_ms:
      Number.isFinite(accumulator.startedMillis) && Number.isFinite(accumulator.endedMillis)
        ? Math.max(0, accumulator.endedMillis - accumulator.startedMillis)
        : null,
    span_count: accumulator.records.length,
    error_count: errorCount,
    status_code: errorCount > 0 ? "STATUS_CODE_ERROR" : statusName(first.span),
    session_id: sessionId,
    model: pick(merged, MODEL_KEYS) ?? null,
    input_tokens: sum(INPUT_TOKEN_KEYS),
    output_tokens: sum(OUTPUT_TOKEN_KEYS),
    received_at: receivedAt,
  };
}

/** One `digitrace_sessions` row per session id in the batch. */
function sessionRow(
  sessionId: string,
  records: SpanRecord[],
  workspaceId: string,
  receivedAt: string,
): Row {
  let firstMillis = Number.POSITIVE_INFINITY;
  let lastMillis = Number.NEGATIVE_INFINITY;
  for (const record of records) {
    const start = nanos(record.span.startTimeUnixNano);
    const end = nanos(record.span.endTimeUnixNano) ?? start;
    if (start !== undefined) firstMillis = Math.min(firstMillis, Number(start / 1_000_000n));
    if (end !== undefined) lastMillis = Math.max(lastMillis, Number(end / 1_000_000n));
  }
  return {
    workspace_id: workspaceId,
    session_id: sessionId,
    first_seen_at: Number.isFinite(firstMillis) ? new Date(firstMillis).toISOString() : null,
    last_seen_at: Number.isFinite(lastMillis) ? new Date(lastMillis).toISOString() : null,
    received_at: receivedAt,
  };
}

/** Every index row for one queue message. */
export function indexRows(
  records: SpanRecord[],
  workspaceId: string,
  receivedAt: string,
): IndexRows {
  if (records.length === 0) return { spans: [], traces: [], sessions: [] };

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

  // Sorting by first start makes the root choice stable across retries even when
  // a trace arrives without a root span in this batch.
  const traces = [...tracesById.values()]
    .sort((a, b) => a.traceId.localeCompare(b.traceId))
    .map((accumulator) => traceRow(accumulator, workspaceId, receivedAt));

  const sessionsById = new Map<string, SpanRecord[]>();
  for (const record of records) {
    const sessionId = pick(
      {
        ...attributesToObject(record.resource.attributes),
        ...attributesToObject(record.span.attributes),
      },
      SESSION_KEYS,
    );
    if (sessionId === undefined) continue;
    const bucket = sessionsById.get(sessionId);
    if (bucket) bucket.push(record);
    else sessionsById.set(sessionId, [record]);
  }
  const sessions = [...sessionsById.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([sessionId, bucket]) => sessionRow(sessionId, bucket, workspaceId, receivedAt));

  // A stable order makes a batch idempotent in its PostgREST payload, which is
  // what an upsert with `merge-duplicates` expects on a retry.
  spans.sort((a, b) =>
    `${String(a.trace_id)}/${String(a.span_id)}`.localeCompare(
      `${String(b.trace_id)}/${String(b.span_id)}`,
    ),
  );

  return { spans, traces, sessions };
}

/** The conflict targets, named once so the migration and the consumer agree. */
export const CONFLICT_TARGETS = {
  traces: "workspace_id,trace_id",
  spans: "workspace_id,trace_id,span_id",
  sessions: "workspace_id,session_id",
} as const;
