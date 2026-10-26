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
  resolveWorkspaceId as defaultResolveWorkspaceId,
  upsertRows as defaultUpsertRows,
} from "./supabase";
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
  const rows = indexRows(records, workspaceId, message.receivedAt);

  await deps.upsertRows(env, "digitrace_traces", rows.traces, CONFLICT_TARGETS.traces);
  await deps.upsertRows(env, "digitrace_spans_index", rows.spans, CONFLICT_TARGETS.spans);
  await deps.upsertRows(env, "digitrace_sessions", rows.sessions, CONFLICT_TARGETS.sessions);

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
      await storeMessage(env, parsed, deps);
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
