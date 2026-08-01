/**
 * DigiChat activity protocol — the vocabulary every backend provider emits and
 * the shared UI renders.
 *
 * Field names follow OpenTelemetry GenAI semantic conventions (`operation` is
 * gen_ai.operation.name, `toolName` is gen_ai.tool.name) so these same events can
 * later feed a real OTLP exporter without inventing a second vocabulary. The
 * exporter itself is deliberately out of scope for this phase — no collector is
 * configured anywhere in the repo yet.
 *
 * IMPORTANT: this type IS the disclosure allowlist. It has no field for an
 * upstream endpoint, model id, raw prompt, or upstream error body, so a provider
 * cannot leak internals to a public anonymous embed by accident. Anything worth
 * surfacing must pass through a declared field.
 *
 * Spec: docs/superpowers/specs/2026-08-01-digichat-activity-protocol-design.md
 */

export const ACTIVITY_PART_TYPE = "data-digichatActivity" as const;

export const MAX_LABEL_CHARS = 200;
export const MAX_QUERY_CHARS = 200;
export const MAX_DOCUMENTS = 8;
export const MAX_DOC_FIELD_CHARS = 300;
export const MAX_REASONING_CHARS = 4000;

export type ActivityDetail = "off" | "labels" | "full";

export type ActivityDocument = { title: string; path: string };

export type ActivitySpan = {
  /** gen_ai.operation.name */
  operation: "execute_tool" | "retrieve" | "chat";
  /** gen_ai.tool.name */
  toolName?: string;
  query?: string;
  status: "started" | "completed" | "failed";
  /** Presentation-safe; never raw upstream text. */
  label: string;
  documents?: ActivityDocument[];
  reasoningDelta?: string;
};

const OPERATIONS = ["execute_tool", "retrieve", "chat"] as const;
const STATUSES = ["started", "completed", "failed"] as const;

function str(value: unknown, max: number): string | undefined {
  if (typeof value !== "string") return undefined;
  const trimmed = value.trim();
  if (!trimmed) return undefined;
  return trimmed.slice(0, max);
}

function documents(value: unknown): ActivityDocument[] | undefined {
  if (!Array.isArray(value)) return undefined;
  const out: ActivityDocument[] = [];
  for (const entry of value) {
    if (!entry || typeof entry !== "object" || Array.isArray(entry)) continue;
    const record = entry as Record<string, unknown>;
    const title = str(record.title, MAX_DOC_FIELD_CHARS);
    const path = str(record.path, MAX_DOC_FIELD_CHARS);
    if (!title || !path) continue;
    out.push({ title, path });
    if (out.length === MAX_DOCUMENTS) break;
  }
  return out.length ? out : undefined;
}

/**
 * Rebuilds a span from scratch out of declared fields only. Undeclared keys are
 * not stripped so much as never copied — that is what makes this an allowlist
 * rather than a denylist that a new provider field could slip past.
 */
export function sanitizeActivitySpan(input: unknown): ActivitySpan | null {
  if (!input || typeof input !== "object" || Array.isArray(input)) return null;
  const record = input as Record<string, unknown>;

  const operation = OPERATIONS.find((o) => o === record.operation);
  const status = STATUSES.find((s) => s === record.status);
  const label = str(record.label, MAX_LABEL_CHARS);
  if (!operation || !status || !label) return null;

  const span: ActivitySpan = { operation, status, label };

  const toolName = str(record.toolName, MAX_LABEL_CHARS);
  if (toolName) span.toolName = toolName;

  const query = str(record.query, MAX_QUERY_CHARS);
  if (query) span.query = query;

  const docs = documents(record.documents);
  if (docs) span.documents = docs;

  const reasoningDelta = str(record.reasoningDelta, MAX_REASONING_CHARS);
  if (reasoningDelta) span.reasoningDelta = reasoningDelta;

  return span;
}

/**
 * Server-side detail gate. Applied before the span is written to the stream, so
 * `off` and `labels` tenants never receive documents or reasoning over the wire.
 */
export function applyActivityDetail(
  span: ActivitySpan,
  detail: ActivityDetail
): ActivitySpan | null {
  if (detail === "off") return null;
  if (detail === "full") return span;
  const { documents: _documents, reasoningDelta: _reasoning, ...rest } = span;
  void _documents;
  void _reasoning;
  return rest;
}
