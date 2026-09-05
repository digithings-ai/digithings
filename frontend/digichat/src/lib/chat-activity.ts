/**
 * digichat activity protocol — the vocabulary every backend provider emits and
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

import type { DigiChatActivity } from "@digithings/digichat-ui";
import type { UIMessage } from "ai";

/** @deprecated 1.4 wire type — 2.0 does not emit this. Kept to hydrate old transcripts. */
export const ACTIVITY_PART_TYPE = "data-digichatActivity" as const;

export const MAX_LABEL_CHARS = 200;
export const MAX_QUERY_CHARS = 200;
export const MAX_DOCUMENTS = 20;
export const MAX_DOC_FIELD_CHARS = 300;
export const MAX_REASONING_CHARS = 4000;
export const MAX_SNIPPET_CHARS = 280;
export const MAX_NOTE_BODY_CHARS = 80_000;
export const MAX_BRIEF_THEMES = 8;
export const MAX_BRIEF_QUESTIONS = 12;
export const MAX_BRIEF_THEME_LABEL = 120;
export const MAX_BRIEF_THEME_SUMMARY = 220;
export const MAX_BRIEF_QUESTION_CHARS = 200;

export type ActivityDetail = "off" | "labels" | "full";

export type ActivityDocument = {
  title: string;
  path: string;
  tier?: string;
  year?: number;
  snippet?: string;
  /** Full note from digivault_get_note. Not an invented URL. */
  body?: string;
};

export type ActivityBrief = {
  themes: { label: string; summary: string }[];
  questions?: string[];
};

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
  /**
   * Set by applyActivityDetail (never by a provider) when this span originally
   * carried documents that the `labels` gate stripped. Carries no upstream
   * data — it is a derived boolean, not a disclosure — but lets the projector
   * tell "the search really found nothing" apart from "results exist but this
   * tenant's detail level withholds them," so it does not misreport a real
   * hit as a no-hits result.
   */
  documentsWithheld?: boolean;
  brief?: ActivityBrief;
  /**
   * Upstream hit count when source mapping yielded no documents (e.g. digisearch
   * returned sources without usable path/title). Used only when `documents` is
   * empty so a positive search is not misreported as "no hits".
   */
  hitCount?: number;
};

const OPERATIONS = ["execute_tool", "retrieve", "chat"] as const;
const STATUSES = ["started", "completed", "failed"] as const;

function str(value: unknown, max: number): string | undefined {
  if (typeof value !== "string") return undefined;
  const trimmed = value.trim();
  if (!trimmed) return undefined;
  return trimmed.slice(0, max);
}

/**
 * Cap a snippet at `max` chars, marking a real cut with a trailing "…" — a bare slice
 * is indistinguishable from a note that just happens to be exactly this short, and the
 * source note behind this snippet can run to thousands of characters (mirrors the
 * backend's own truncation-signal fix for the model-facing payload,
 * digigraph/orchestration/builtin.py's _mark_truncated_excerpts — this is the same
 * problem one layer up, for the human reading the activity panel instead of the model).
 *
 * The ellipsis is RESERVED space (slice to max - 1, then append), not appended after an
 * already-max-length slice — appending after would make the string max + 1 chars, and
 * any downstream re-clip to `max` (this same MAX_SNIPPET_CHARS constant is re-applied
 * when a wire payload is re-parsed) would cut the marker back off.
 */
function snippetStr(value: unknown, max: number): string | undefined {
  if (typeof value !== "string") return undefined;
  const trimmed = value.trim();
  if (!trimmed) return undefined;
  if (trimmed.length <= max) return trimmed.slice(0, max);
  return trimmed.slice(0, max - 1).trimEnd() + "…";
}

function bool(value: unknown): true | undefined {
  return value === true ? true : undefined;
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
    const doc: ActivityDocument = { title, path };
    const tier = str(record.tier, MAX_DOC_FIELD_CHARS);
    if (tier) doc.tier = tier;
    if (typeof record.year === "number" && Number.isFinite(record.year)) {
      doc.year = Math.trunc(record.year);
    }
    const snippet = snippetStr(record.snippet, MAX_SNIPPET_CHARS);
    if (snippet) doc.snippet = snippet;
    const body = snippetStr(record.body, MAX_NOTE_BODY_CHARS);
    if (body) doc.body = body;
    out.push(doc);
    if (out.length === MAX_DOCUMENTS) break;
  }
  return out.length ? out : undefined;
}

function brief(value: unknown): ActivityBrief | undefined {
  if (!value || typeof value !== "object" || Array.isArray(value)) return undefined;
  const record = value as Record<string, unknown>;
  if (!Array.isArray(record.themes)) return undefined;
  const themes: { label: string; summary: string }[] = [];
  for (const entry of record.themes) {
    if (!entry || typeof entry !== "object" || Array.isArray(entry)) continue;
    const t = entry as Record<string, unknown>;
    const label = str(t.label, MAX_BRIEF_THEME_LABEL);
    const summary = str(t.summary, MAX_BRIEF_THEME_SUMMARY);
    if (!label || !summary) continue;
    themes.push({ label, summary });
    if (themes.length === MAX_BRIEF_THEMES) break;
  }
  if (!themes.length) return undefined;
  const out: ActivityBrief = { themes };
  if (Array.isArray(record.questions)) {
    const questions: string[] = [];
    for (const q of record.questions) {
      const s = str(q, MAX_BRIEF_QUESTION_CHARS);
      if (!s) continue;
      questions.push(s);
      if (questions.length === MAX_BRIEF_QUESTIONS) break;
    }
    if (questions.length) out.questions = questions;
  }
  return out;
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

  const briefVal = brief(record.brief);
  if (briefVal) span.brief = briefVal;

  const documentsWithheld = bool(record.documentsWithheld);
  if (documentsWithheld) span.documentsWithheld = documentsWithheld;

  if (
    typeof record.hitCount === "number" &&
    Number.isFinite(record.hitCount) &&
    record.hitCount > 0
  ) {
    span.hitCount = Math.trunc(record.hitCount);
  }

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
  const { documents, reasoningDelta: _reasoning, brief: _brief, ...rest } = span;
  void _reasoning;
  void _brief;
  // A retrieve span only ever carries documents when the search genuinely
  // found something (see the providers). Flag that this rest object had real
  // hits stripped, so the projector can render an honest "search happened"
  // row instead of a fabricated zero count (see toDigiChatActivity).
  return documents && documents.length > 0 ? { ...rest, documentsWithheld: true } : rest;
}

/**
 * Builds a `chat`-operation span from a raw upstream label/status pair,
 * capping the label to MAX_LABEL_CHARS before it ever reaches the stream —
 * the client only truncates at render, so without this an unbounded upstream
 * label would reach the browser verbatim — then runs it through the detail
 * gate. Both SSE providers (digigraph, external relay) otherwise build
 * near-identical spans from a raw label + status; this keeps that
 * construction, and its cap, in one place.
 */
export function chatActivitySpan(
  label: unknown,
  status: ActivitySpan["status"],
  detail: ActivityDetail
): ActivitySpan | null {
  const safeLabel = str(label, MAX_LABEL_CHARS) ?? "activity";
  return applyActivityDetail({ operation: "chat", status, label: safeLabel }, detail);
}

const KEY_SEP = "\x1f";
const toolKey = (name: string, query: string) => `${name}${KEY_SEP}${query}`;

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

/**
 * Rebuild ActivitySpan[] from 2.0 standard UI parts (tool / source / reasoning /
 * data-status). Used so ChatActivities and markdown export keep working without
 * branded wire types.
 */
export function standardPartsToSpans(
  parts: UIMessage["parts"],
): ActivitySpan[] {
  const spans: ActivitySpan[] = [];
  let sawRetrieve = false;

  for (const part of parts) {
    if (part.type === "reasoning") {
      const text = "text" in part && typeof part.text === "string" ? part.text : "";
      if (text) {
        spans.push({
          operation: "chat",
          status: "completed",
          label: "Thinking",
          reasoningDelta: text,
        });
      }
      continue;
    }

    if (part.type === "data-status") {
      const data = "data" in part ? part.data : undefined;
      if (!isRecord(data)) continue;
      const label = typeof data.label === "string" ? data.label : "activity";
      const status: ActivitySpan["status"] =
        data.status === "failed" || data.status === "started" || data.status === "completed"
          ? data.status
          : "completed";
      const span: ActivitySpan = { operation: "chat", status, label };
      if (isRecord(data.brief)) {
        const briefVal = brief(data.brief);
        if (briefVal) span.brief = briefVal;
      }
      spans.push(span);
      continue;
    }

    if (
      part.type === "dynamic-tool" ||
      (typeof part.type === "string" && part.type.startsWith("tool-"))
    ) {
      const name =
        part.type === "dynamic-tool"
          ? ("toolName" in part && typeof part.toolName === "string" && part.toolName
              ? part.toolName
              : "tool")
          : part.type.slice("tool-".length) || "tool";
      const input = "input" in part && isRecord(part.input) ? part.input : {};
      const output = "output" in part && isRecord(part.output) ? part.output : undefined;
      const state = "state" in part ? String(part.state) : "";
      const queryRaw = output?.query ?? input.query;
      const query = typeof queryRaw === "string" ? queryRaw : undefined;
      const label =
        (typeof output?.label === "string" && output.label) ||
        (typeof input.label === "string" && input.label) ||
        name;

      if (
        output &&
        (Array.isArray(output.documents) ||
          output.documentsWithheld === true ||
          typeof output.hitCount === "number")
      ) {
        sawRetrieve = true;
        const docs = documents(output.documents);
        const span: ActivitySpan = {
          operation: "retrieve",
          status: output.status === "failed" ? "failed" : "completed",
          label,
          toolName: name,
        };
        if (query) span.query = query;
        if (docs) span.documents = docs;
        if (output.documentsWithheld === true) span.documentsWithheld = true;
        if (typeof output.hitCount === "number" && Number.isFinite(output.hitCount) && output.hitCount > 0) {
          span.hitCount = Math.trunc(output.hitCount);
        }
        spans.push(span);
        continue;
      }

      const status: ActivitySpan["status"] =
        output?.status === "failed"
          ? "failed"
          : output?.status === "completed" || state === "output-available"
            ? "completed"
            : "started";
      const span: ActivitySpan = { operation: "execute_tool", status, label, toolName: name };
      if (query) span.query = query;
      spans.push(span);
      continue;
    }
  }

  if (!sawRetrieve) {
    const docs: ActivityDocument[] = [];
    for (const part of parts) {
      if (part.type === "source-url") {
        const url = "url" in part && typeof part.url === "string" ? part.url : "";
        const title =
          "title" in part && typeof part.title === "string" && part.title
            ? part.title
            : url;
        if (url) docs.push({ title, path: url });
      } else if (part.type === "source-document") {
        const filename =
          "filename" in part && typeof part.filename === "string" ? part.filename : "";
        const title =
          "title" in part && typeof part.title === "string" && part.title
            ? part.title
            : filename || "document";
        const path = filename || title;
        docs.push({ title, path });
      }
    }
    if (docs.length) {
      spans.push({
        operation: "retrieve",
        status: "completed",
        label: "Sources",
        documents: docs,
      });
    }
  }

  return spans;
}

export type ToDigiChatActivityOptions = {
  /**
   * When true (default), a completed search with no retrieve yet becomes a
   * zero-hit `tool_result`. Mid-stream that flashes "no hits" before documents
   * arrive — pass `settle: false` while the turn is still open so the row stays
   * a running `tool_call` (query visible, status pulsing) until retrieve or the
   * turn settles.
   */
  settle?: boolean;
};

/**
 * Projects provider spans onto the union the shared UI renders.
 *
 * Called over the whole span list on each render (not incrementally), which is
 * what lets the trailing pass rewrite a finished-but-empty search into a
 * "no hits" row: whether citations followed is only knowable once the list ends
 * *and* the turn has settled (`settle: true`).
 */
export function toDigiChatActivity(
  spans: ActivitySpan[],
  opts: ToDigiChatActivityOptions = {},
): DigiChatActivity[] {
  const settle = opts.settle !== false;
  const rows: DigiChatActivity[] = [];
  const toolRows = new Map<string, number>();
  const traceRows = new Map<string, number>();
  const completedTools = new Set<string>();
  // Keys whose terminal execute_tool span was "failed" rather than
  // "completed" — checked by the trailing pass so an error renders as an
  // honest failure row instead of the literal "no hits" a real empty search
  // gets. Membership here does not imply the tool is still unresolved: a
  // retrieve arriving afterwards overwrites the row before the trailing pass
  // ever runs, and the pass only looks at rows still shaped like a tool_call.
  const failedTools = new Set<string>();
  // Row index of the still-open ("started", not yet resolved by a matching
  // completed/failed/retrieve span) call for each tool name — regardless of
  // whether the started span itself carried a query. Cleared the instant a
  // completed/failed span OR a retrieve span resolves it, so a later,
  // unrelated "started" for the same tool can never be mistaken for a
  // callback that belongs to an earlier, already-resolved invocation.
  const pendingRow = new Map<string, number>();
  // Placeholder rows whose invocation turned out to duplicate an already-
  // tracked (toolName, query) call. Repeating an identical search is the same
  // logical row in the UI, so its own placeholder is redundant and is dropped
  // at the end rather than left behind as a phantom "Searching…" row.
  const orphanedRows = new Set<number>();
  let pendingTool = "search";
  let pendingQuery = "";
  let reasoning = "";

  for (const span of spans) {
    if (span.reasoningDelta) {
      reasoning += span.reasoningDelta;
      // CONSTRAINT: this returns before any other field on the span is read.
      // A span carrying BOTH reasoningDelta and, say, documents/query would
      // silently lose those other fields — only the reasoning text survives.
      // No Phase 1 provider emits such a span, but Phase 2's digivault
      // streams reasoning deltas and could. If a future provider needs both
      // on one logical step, emit two spans rather than teaching this branch
      // to fall through.
      continue;
    }

    if (span.operation === "execute_tool") {
      const name = span.toolName ?? "tool";
      pendingTool = name;
      if (span.query) pendingQuery = span.query;

      if (span.status === "started") {
        // Reuse the tool's still-open placeholder rather than opening a
        // second one for the same in-flight (query not yet known) call.
        if (!pendingRow.has(name)) {
          rows.push({ kind: "tool_call", name, query: span.query ?? "" });
          pendingRow.set(name, rows.length - 1);
        }
        continue;
      }

      // "failed" is terminal too — a search that errored must not render as a
      // tool call that never finishes, and must not be mistaken for a real
      // empty result either (see failedTools above).
      const key = toolKey(name, span.query ?? "");
      completedTools.add(key);
      if (span.status === "failed") failedTools.add(key);
      const idx = pendingRow.get(name);
      pendingRow.delete(name);

      if (toolRows.has(key)) {
        // A repeat of an identical (tool, query) search — it already has a
        // row. This invocation's own placeholder, if any, is now orphaned.
        if (idx !== undefined) orphanedRows.add(idx);
        continue;
      }

      if (idx !== undefined) {
        const row = rows[idx];
        if (row.kind === "tool_call") row.query = span.query ?? "";
        toolRows.set(key, idx);
      } else {
        rows.push({ kind: "tool_call", name, query: span.query ?? "" });
        toolRows.set(key, rows.length - 1);
      }
      continue;
    }

    if (span.operation === "retrieve") {
      const name = span.toolName ?? pendingTool;
      const query = span.query ?? pendingQuery;
      const hits = span.documents ?? [];
      const key = toolKey(name, query);
      // Failed retrieve must never fall through to hitCount-as-success —
      // digivault all-error batches previously set status=failed with
      // hitCount=errorCount and rendered as N successful hits.
      if (span.status === "failed") {
        const failResult: DigiChatActivity = {
          kind: "status",
          message: query ? `Search for "${query}" failed.` : "Search failed.",
        };
        const failIdx = toolRows.get(key);
        const pending = pendingRow.get(name);
        pendingRow.delete(name);
        completedTools.delete(key);
        failedTools.add(key);
        if (failIdx !== undefined) {
          rows[failIdx] = failResult;
        } else if (pending !== undefined) {
          rows[pending] = failResult;
          toolRows.set(key, pending);
        } else {
          rows.push(failResult);
          toolRows.set(key, rows.length - 1);
        }
        continue;
      }
      // `labels` detail: applyActivityDetail already stripped the documents
      // server-side, but a retrieve span is only ever emitted when the search
      // genuinely found something (see the providers) — so hits: [] here
      // would misreport a real result as "no hits" (the shared UI renders
      // count === 0 as the literal string `no hits for "…"`). Render an
      // honest "search happened" status row instead of a fabricated count.
      // When mapping dropped every source but upstream hit_count was positive,
      // prefer that count over documents.length so the UI does not say "no hits".
      const count =
        hits.length > 0
          ? hits.length
          : typeof span.hitCount === "number" && span.hitCount > 0
            ? span.hitCount
            : 0;
      const result: DigiChatActivity = span.documentsWithheld
        ? {
            kind: "status",
            message: query ? `Found results for "${query}".` : "Search completed.",
          }
        : { kind: "tool_result", name, query, hits, count };
      const idx = toolRows.get(key);
      if (idx !== undefined) {
        const existing = rows[idx];
        if (
          existing.kind === "tool_result" &&
          result.kind === "tool_result" &&
          !span.documentsWithheld
        ) {
          const mergedHits = [...existing.hits];
          for (const hit of result.hits) {
            const existingIdx = mergedHits.findIndex((h) => h.path === hit.path);
            if (existingIdx === -1) {
              mergedHits.push(hit);
            } else if (hit.body && !mergedHits[existingIdx].body) {
              mergedHits[existingIdx] = { ...mergedHits[existingIdx], ...hit };
            }
          }
          // CodeRabbit finding (#2327 review): mergedHits.length is 0 whenever
          // both sides are hitCount-only spans (no structured hits at all, e.g.
          // repeated digivault_get_note rounds) — unconditionally using it here
          // silently dropped a genuinely positive count to 0, exactly the
          // "no hits" misreport documentsWithheld exists elsewhere to prevent.
          // Prefer mergedHits.length once real hits exist; otherwise carry
          // forward whichever side had a positive hitCount-derived count.
          const mergedCount =
            mergedHits.length > 0 ? mergedHits.length : Math.max(existing.count, result.count);
          rows[idx] = { ...result, hits: mergedHits, count: mergedCount };
        } else {
          rows[idx] = result;
        }
      } else {
        // No existing row for this (tool, query) — but a still-open "started"
        // placeholder for this tool name (an execute_tool span that never got
        // a matching completed/failed event, e.g. Foundry citations arriving
        // straight off the message with no intervening file_search_call
        // completion) is this same call settling via retrieve directly.
        // Resolve it in place rather than pushing a second row and leaving
        // the placeholder to spin forever.
        const pending = pendingRow.get(name);
        if (pending !== undefined) {
          rows[pending] = result;
          pendingRow.delete(name);
          toolRows.set(key, pending);
        } else {
          rows.push(result);
          toolRows.set(key, rows.length - 1);
        }
      }
      completedTools.delete(key);
      continue;
    }

    if (span.brief) {
      rows.push({
        kind: "brief",
        themes: span.brief.themes,
        ...(span.brief.questions ? { questions: span.brief.questions } : {}),
      });
      continue;
    }

    // operation === "chat": an opaque upstream step. Collapse by label so a
    // provider re-emitting the same step does not stack duplicate rows.
    const key = span.label;
    const done = span.status !== "started";
    const idx = traceRows.get(key);
    if (idx !== undefined) {
      const row = rows[idx];
      if (row.kind === "trace") row.done = row.done || done;
      continue;
    }
    rows.push({ kind: "trace", label: span.label, done });
    traceRows.set(key, rows.length - 1);
  }

  // A search that completed and never produced citations is a "no hits" answer,
  // not a perpetually-pending tool call — but only once the turn has settled.
  // Mid-stream the call `.done` often arrives a few events before the output
  // `.done`; converting early flashes "no hits" then rewrites to real hits.
  // A search that errored is terminal either way — never leave it spinning,
  // and never pretend it ran clean with zero hits.
  for (const [key, idx] of toolRows) {
    const row = rows[idx];
    if (row.kind !== "tool_call" || !completedTools.has(key)) continue;
    if (failedTools.has(key)) {
      rows[idx] = {
        kind: "status",
        message: row.query ? `Search for "${row.query}" failed.` : "Search failed.",
      };
      continue;
    }
    if (settle) {
      rows[idx] = { kind: "tool_result", name: row.name, query: row.query, hits: [], count: 0 };
    }
  }

  if (reasoning) rows.push({ kind: "reasoning", text: reasoning });
  return orphanedRows.size ? rows.filter((_, idx) => !orphanedRows.has(idx)) : rows;
}

export function messageActivities(
  message: UIMessage,
  opts: ToDigiChatActivityOptions = {},
): DigiChatActivity[] {
  const standard = standardPartsToSpans(message.parts);
  if (standard.length) return toDigiChatActivity(standard, opts);

  const spans = message.parts
    .filter(
      (part): part is { type: typeof ACTIVITY_PART_TYPE; data: unknown } =>
        part.type === ACTIVITY_PART_TYPE
    )
    .map((part) => sanitizeActivitySpan(part.data))
    .filter((span): span is ActivitySpan => span !== null);
  return toDigiChatActivity(spans, opts);
}
