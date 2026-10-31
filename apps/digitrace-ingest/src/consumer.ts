/**
 * The Queue consumer.
 *
 * One message is one archive object plus its index rows and its metric points.
 * The order matters: R2 first, because the archive is the system of record
 * (ADR-0036 §3); the index and the aggregates are derived from it.
 *
 * Retry policy: a message that fails is retried individually with a growing
 * delay, and after `max_retries` the queue sends it to the dead-letter queue
 * declared in wrangler.toml. Nothing here throws out of the batch handler, so a
 * single poison message cannot send the healthy messages of the same batch back
 * through the queue. A message whose *shape* is wrong can never succeed, so it
 * is acknowledged and logged rather than retried — a retry loop is not a record.
 */
import { writeSpanMetric, spanMetrics } from "./analytics";
import { CONFLICT_TARGETS, indexRows, type IndexRows } from "./index-rows";
import {
  refreshTraceRow as defaultRefreshTraceRow,
  resolveWorkspaceId as defaultResolveWorkspaceId,
  upsertRows as defaultUpsertRows,
} from "./d1";
import type { ArchiveLine, Env, IngestMessage, SpanRecord } from "./types";

/** The longest delay between attempts, in seconds. */
export const MAX_RETRY_DELAY_SECONDS = 300;
/** The first retry delay, in seconds. */
export const BASE_RETRY_DELAY_SECONDS = 15;

export interface ConsumerDeps {
  putObject: (
    bucket: R2Bucket,
    key: string,
    body: string,
    metadata: Record<string, string>,
  ) => Promise<void>;
  resolveWorkspaceId: (env: Env, slug: string) => Promise<string>;
  upsertRows: (
    env: Env,
    table: string,
    rows: Array<Record<string, unknown>>,
    onConflict: string,
  ) => Promise<void>;
  refreshTraceRow: (env: Env, workspaceId: string, traceId: string) => Promise<void>;
  writeSpanMetric: typeof writeSpanMetric;
}

const defaultDeps: ConsumerDeps = {
  putObject: async (bucket, key, body, metadata) => {
    await bucket.put(key, body, {
      httpMetadata: { contentType: "application/x-ndjson" },
      customMetadata: metadata,
    });
  },
  resolveWorkspaceId: (env, slug) => defaultResolveWorkspaceId(env, slug),
  upsertRows: (env, table, rows, onConflict) => defaultUpsertRows(env, table, rows, onConflict),
  refreshTraceRow: (env, workspaceId, traceId) => defaultRefreshTraceRow(env, workspaceId, traceId),
  writeSpanMetric,
};

/** Back-off for a message that has already failed `attempts` times. */
export function retryDelaySeconds(attempts: number): number {
  const exponent = Math.max(0, Math.min(attempts - 1, 5));
  return Math.min(BASE_RETRY_DELAY_SECONDS * 2 ** exponent, MAX_RETRY_DELAY_SECONDS);
}

const SLUG = /^[a-z0-9][a-z0-9-]{0,62}$/;

/**
 * A message as this consumer understands it, or undefined when it is not one.
 *
 * The key must also live under the message's own tenant prefix. That check is
 * defence in depth, not the tenant boundary (the receiver already decided the
 * tenant from the token): it means a malformed or tampered message can never
 * write an object into another tenant's prefix.
 */
export function parseMessage(body: unknown): IngestMessage | undefined {
  if (typeof body !== "object" || body === null) return undefined;
  const message = body as Partial<IngestMessage>;
  if (message.v !== 1) return undefined;
  if (typeof message.tenant !== "string" || !SLUG.test(message.tenant)) return undefined;
  if (typeof message.source !== "string" || message.source === "") return undefined;
  if (typeof message.ndjson !== "string" || message.ndjson === "") return undefined;
  if (typeof message.archiveKey !== "string") return undefined;
  if (!message.archiveKey.startsWith(`tenant=${message.tenant}/date=`)) return undefined;
  if (typeof message.receivedAt !== "string") return undefined;
  if (typeof message.batchId !== "string" || message.batchId === "") return undefined;
  if (typeof message.chunk !== "number" || typeof message.chunks !== "number") return undefined;
  if (
    message.incompleteTraces !== undefined &&
    (!Array.isArray(message.incompleteTraces) ||
      message.incompleteTraces.some((id) => typeof id !== "string" || id === ""))
  ) {
    return undefined;
  }
  return {
    v: 1,
    batchId: message.batchId,
    chunk: message.chunk,
    chunks: message.chunks,
    tenant: message.tenant,
    tenantSlugVerified: message.tenantSlugVerified === true,
    source: message.source,
    receivedAt: message.receivedAt,
    archiveKey: message.archiveKey,
    ...(Array.isArray(message.incompleteTraces) && message.incompleteTraces.length > 0
      ? { incompleteTraces: [...message.incompleteTraces] }
      : {}),
    ndjson: message.ndjson,
  };
}

/** The span records a message carries, skipping any line that will not parse. */
export function recordsFromNdjson(ndjson: string): SpanRecord[] {
  const records: SpanRecord[] = [];
  for (const line of ndjson.split("\n")) {
    if (line.trim() === "") continue;
    let parsed: ArchiveLine;
    try {
      parsed = JSON.parse(line) as ArchiveLine;
    } catch {
      continue;
    }
    if (!parsed || typeof parsed !== "object" || !parsed.span) continue;
    if (typeof parsed.span.traceId !== "string" || typeof parsed.span.spanId !== "string") {
      continue;
    }
    records.push({
      resource: parsed.resource ?? {},
      scope: parsed.scope ?? {},
      span: parsed.span,
    });
  }
  return records;
}

/** Write one message's objects and rows. Throws so the caller can retry. */
export async function storeMessage(
  env: Env,
  message: IngestMessage,
  deps: ConsumerDeps,
): Promise<IndexRows> {
  await deps.putObject(env.ARCHIVE, message.archiveKey, message.ndjson, {
    tenant: message.tenant,
    tenant_slug_verified: String(message.tenantSlugVerified),
    source: message.source,
    batch_id: message.batchId,
    chunk: `${message.chunk}/${message.chunks}`,
  });

  const records = recordsFromNdjson(message.ndjson);
  const workspaceId = await deps.resolveWorkspaceId(env, message.tenant);
  const rows = indexRows(records, workspaceId, message.receivedAt, message.source);

  // Two tables, not four. `digitrace_scores` is MLflow's write-back, and
  // `digitrace_sessions` carries cross-batch counters that a REST upsert can
  // only overwrite — see the header of `index-rows.ts`.
  //
  // The trace row is inserted from this message and then **recomputed from the
  // spans index**, because this message may not hold the whole trace: a trace
  // over the message budget has its slice named in `incompleteTraces`, and a
  // trace exported across several OTLP requests has earlier slices already in
  // the table. the trace recompute (`REFRESH_TRACE_SQL`) is UPDATE-only, so the insert is
  // required; the recompute is what makes `span_count`, the time range, the
  // root name and the sticky error true over all spans, not this slice.
  await deps.upsertRows(env, "digitrace_traces", rows.traces, CONFLICT_TARGETS.traces);
  await deps.upsertRows(env, "digitrace_spans_index", rows.spans, CONFLICT_TARGETS.spans);

  const traceIds = [...new Set(rows.traces.map((row) => String(row.trace_id)))];
  await Promise.all(traceIds.map((traceId) => deps.refreshTraceRow(env, workspaceId, traceId)));

  for (const record of records) {
    deps.writeSpanMetric(env.ANALYTICS, spanMetrics(record, message.tenant, message.source));
  }

  return rows;
}

/**
 * The queue handler.
 *
 * Every message is handled independently: one failure retries that message only.
 */
export async function handleQueue(
  batch: MessageBatch<IngestMessage>,
  env: Env,
  overrides: Partial<ConsumerDeps> = {},
): Promise<void> {
  const deps: ConsumerDeps = { ...defaultDeps, ...overrides };

  // One workspace lookup per tenant per batch. A batch is up to ten messages
  // from the same source, so re-resolving the slug per message is ten identical
  // reads of `workspaces`; a rejected lookup is evicted so one failure does not
  // poison the rest of the batch.
  const workspaces = new Map<string, Promise<string>>();
  const batchDeps: ConsumerDeps = {
    ...deps,
    resolveWorkspaceId: (env, slug) => {
      let pending = workspaces.get(slug);
      if (!pending) {
        pending = deps.resolveWorkspaceId(env, slug).catch((error: unknown) => {
          workspaces.delete(slug);
          throw error;
        });
        workspaces.set(slug, pending);
      }
      return pending;
    },
  };

  for (const message of batch.messages) {
    const parsed = parseMessage(message.body);
    if (!parsed) {
      // Malformed shape: retrying cannot fix it. The id is logged so the message
      // is findable; the body is not logged, because it carries span content.
      console.warn("digitrace-ingest: dropping unparseable queue message", {
        messageId: message.id,
      });
      message.ack();
      continue;
    }

    try {
      await storeMessage(env, parsed, batchDeps);
    } catch (error) {
      // The reason is logged without any message content or credential. The
      // queue keeps the attempt count and the DLQ keeps the body.
      console.warn("digitrace-ingest: message retry", {
        messageId: message.id,
        attempts: message.attempts,
        reason: error instanceof Error ? error.message : "unknown error",
      });
      message.retry({ delaySeconds: retryDelaySeconds(message.attempts) });
    }
  }
}
