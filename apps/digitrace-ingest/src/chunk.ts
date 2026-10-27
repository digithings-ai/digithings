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
 *
 * Records are packed **by trace id, never across one**. The `digitrace_traces`
 * row is a cross-span aggregate (`span_count`, the time range, `name`,
 * `status`), so a message boundary through the middle of a trace would let the
 * later message replace the row with its own slice — a smaller `span_count`, a
 * duration that never happened, and a `name` from a span that is not the root.
 * One trace only crosses a boundary when it alone exceeds the budget; those
 * trace ids are listed in `incompleteTraces`, so the message states where its
 * aggregate stops. The consumer inserts the partial row and then recomputes it
 * from the spans index (`refresh_digitrace_trace`), which makes the row true
 * over every span of the trace again.
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

interface PreparedLine {
  line: ArchiveLine;
  size: number;
}

interface PendingChunk {
  lines: ArchiveLine[];
  key: string;
  /** Trace ids this chunk cannot carry in full; empty for every whole trace. */
  incomplete: Set<string>;
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
  let incomplete = new Set<string>();

  const flush = () => {
    if (lines.length === 0) return;
    chunks.push({
      lines,
      key: archiveKey(meta.tenant, meta.receivedAt, meta.source, newUuid()),
      incomplete,
    });
    lines = [];
    bytes = 0;
    incomplete = new Set<string>();
  };

  // Group first, so a trace's spans can never be separated by a byte boundary.
  // First-seen order is kept, which makes the split deterministic.
  const groups = new Map<string, PreparedLine[]>();
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
    const traceId = record.span.traceId;
    const group = groups.get(traceId);
    if (group) group.push({ line, size });
    else groups.set(traceId, [{ line, size }]);
  }

  for (const [traceId, group] of groups) {
    const groupBytes = group.reduce((total, item) => total + item.size, 0);
    if (groupBytes <= MAX_NDJSON_BYTES) {
      if (lines.length > 0 && bytes + groupBytes > MAX_NDJSON_BYTES) flush();
      for (const item of group) {
        lines.push(item.line);
        bytes += item.size;
      }
      continue;
    }
    // One trace alone exceeds a message. It has to be split, and no slice can
    // claim the aggregate, so every chunk carrying part of it is marked.
    for (const item of group) {
      if (lines.length > 0 && bytes + item.size > MAX_NDJSON_BYTES) flush();
      lines.push(item.line);
      bytes += item.size;
      incomplete.add(traceId);
    }
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
      ...(chunk.incomplete.size > 0
        ? { incompleteTraces: [...chunk.incomplete].sort((a, b) => a.localeCompare(b)) }
        : {}),
    });
  });

  return { messages, droppedOversizedSpans };
}
