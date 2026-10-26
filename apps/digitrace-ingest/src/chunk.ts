/**
 * Splitting one request into queue messages.
 *
 * Cloudflare Queues caps a message at 128 KiB (and a batch at 256 KiB), while an
 * OTLP export can be megabytes. So a request becomes as many messages as it
 * takes, each one already an archive object.
 *
 * The budget below is on the NDJSON *before* the message is JSON-encoded, and it
 * is deliberately half the queue limit: JSON encoding a string escapes `"` and
 * `\` to two bytes each, so a 56 KiB NDJSON body cannot serialise past
 * 112 KiB plus a small envelope, however hostile the span text is. A tighter
 * budget would be a bigger number of smaller objects; this one keeps an ordinary
 * request to one object.
 *
 * A single span bigger than `MAX_SPAN_LINE_BYTES` is dropped and reported,
 * because it cannot be carried in one queue message and splitting a span across
 * messages would break the row. That is the only loss path in the receiver, and
 * its count reaches the source in the OTLP `partialSuccess` response.
 */
import { archiveKey, archiveLine, messageFor } from "./archive";
import type { ArchiveLine, IngestMessage, SpanRecord } from "./types";

/** The Queues product's per-message ceiling. */
export const MAX_QUEUE_MESSAGE_BYTES = 128 * 1024;
/** The NDJSON budget for one message; half the ceiling, for JSON escaping. */
export const MAX_NDJSON_BYTES = 56 * 1024;
/** The largest single span line the receiver will carry. */
export const MAX_SPAN_LINE_BYTES = 32 * 1024;

const encoder = new TextEncoder();

export interface ChunkMeta {
  batchId: string;
  tenant: string;
  tenantSlugVerified: boolean;
  source: string;
  receivedAt: string;
}

export interface ChunkResult {
  messages: IngestMessage[];
  droppedOversizedSpans: number;
}

interface PendingChunk {
  lines: ArchiveLine[];
  key: string;
}

/**
 * Split records into queue messages, one archive object each.
 *
 * @param newUuid injected so a test is deterministic; production passes
 *   `crypto.randomUUID`. The uuid is generated here, at receive time, so a queue
 *   retry rewrites the same object instead of creating a duplicate.
 */
export function chunkSpans(
  records: SpanRecord[],
  meta: ChunkMeta,
  newUuid: () => string = () => crypto.randomUUID(),
): ChunkResult {
  const chunks: PendingChunk[] = [];
  let lines: ArchiveLine[] = [];
  let bytes = 0;
  let droppedOversizedSpans = 0;

  const flush = () => {
    if (lines.length === 0) return;
    chunks.push({
      lines,
      key: archiveKey(meta.tenant, meta.receivedAt, meta.source, newUuid()),
    });
    lines = [];
    bytes = 0;
  };

  for (const record of records) {
    const line = archiveLine(record, {
      tenant_slug: meta.tenant,
      tenant_slug_verified: meta.tenantSlugVerified,
      source: meta.source,
      batch_id: meta.batchId,
      // Filled in below, once the chunk count is known.
      chunk: 0,
      chunks: 0,
      received_at: meta.receivedAt,
    });
    const size = encoder.encode(JSON.stringify(line)).length + 1;
    if (size > MAX_SPAN_LINE_BYTES) {
      droppedOversizedSpans += 1;
      continue;
    }
    if (lines.length > 0 && bytes + size > MAX_NDJSON_BYTES) flush();
    lines.push(line);
    bytes += size;
  }
  flush();

  const messages = chunks.map((chunk, index) => {
    // The lines were built before the chunk count was known, so the two
    // position fields are stamped here; every line in an object carries the
    // same pair, which is what makes a lone line readable after a replay.
    for (const line of chunk.lines) {
      line.chunk = index;
      line.chunks = chunks.length;
    }
    return messageFor(chunk.lines, {
      batchId: meta.batchId,
      chunk: index,
      chunks: chunks.length,
      tenant: meta.tenant,
      tenantSlugVerified: meta.tenantSlugVerified,
      source: meta.source,
      receivedAt: meta.receivedAt,
      archiveKey: chunk.key,
    });
  });

  return { messages, droppedOversizedSpans };
}
