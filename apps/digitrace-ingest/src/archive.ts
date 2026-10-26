/**
 * The archive: object key, object body, and the two edge values stamped on every
 * line.
 *
 * ADR-0036 §5: `tenant_slug` and `tenant_slug_verified` are edge values. They
 * are not columns on the index rows; they are carried on the archived record
 * next to the source payload, alongside the key prefix `tenant=<slug>/`. Every
 * line repeats them, so a replay can enumerate a window by prefix and trust each
 * line on its own without a header object to pair it with.
 */
import type { ArchiveLine, IngestMessage, SpanRecord } from "./types";

export const BUCKET = "digitrace-archive";

/** `tenant=<slug>/date=<YYYY-MM-DD>/<source>/<uuid>.ndjson` (ADR-0036 §3). */
export function archiveKey(
  tenant: string,
  receivedAt: string,
  source: string,
  uuid: string,
): string {
  const date = utcDate(receivedAt);
  return `tenant=${tenant}/date=${date}/${source}/${uuid}.ndjson`;
}

/** The UTC calendar date of an ISO timestamp. Throws on an unparseable one. */
export function utcDate(iso: string): string {
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) {
    throw new Error("receivedAt is not a valid timestamp");
  }
  return parsed.toISOString().slice(0, 10);
}

/** One archive line: our edges, the span, and the context it arrived under. */
export function archiveLine(
  record: SpanRecord,
  meta: Pick<
    ArchiveLine,
    | "tenant_slug"
    | "tenant_slug_verified"
    | "source"
    | "batch_id"
    | "chunk"
    | "chunks"
    | "received_at"
  >,
): ArchiveLine {
  return {
    ...meta,
    resource: record.resource,
    scope: record.scope,
    span: record.span,
  };
}

/** The object body: one JSON line per span record, newline-terminated. */
export function toNdjson(lines: ArchiveLine[]): string {
  if (lines.length === 0) return "";
  return `${lines.map((line) => JSON.stringify(line)).join("\n")}\n`;
}

/** The message a chunk becomes, given its lines. */
export function messageFor(
  lines: ArchiveLine[],
  meta: Pick<
    IngestMessage,
    | "batchId"
    | "chunk"
    | "chunks"
    | "tenant"
    | "tenantSlugVerified"
    | "source"
    | "receivedAt"
    | "archiveKey"
  >,
): IngestMessage {
  return { v: 1, ...meta, ndjson: toNdjson(lines) };
}
