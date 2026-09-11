import type { ActivitySpan } from "@/lib/chat-activity";
import { mapRawSourceToDocument } from "./source-document";
import { queryFromToolArgs, toolInputFromPayload } from "./tool-args";

export const DIGIVAULT_SEARCH_TOOL = "digivault_search_notes";
export const DIGIVAULT_GET_NOTE_TOOL = "digivault_get_note";

function vaultPathFromPayload(payload: Record<string, unknown>, documents: { path: string }[]): string | undefined {
  const query =
    typeof payload.query === "string" && payload.query.trim() ? payload.query.trim() : undefined;
  if (query) return query;
  return documents[0]?.path;
}

function loadedNoteLabel(path?: string): string {
  return path ? `Loaded full note: ${path}` : "Loaded full note";
}

function attachToolArgs(
  span: ActivitySpan,
  payload: Record<string, unknown>,
): ActivitySpan {
  const toolInput = toolInputFromPayload(payload);
  const query =
    span.query ||
    (typeof payload.query === "string" && payload.query.trim()
      ? payload.query.trim()
      : undefined) ||
    (toolInput ? queryFromToolArgs(toolInput) : undefined);
  return {
    ...span,
    ...(query ? { query } : {}),
    ...(toolInput ? { toolInput } : query ? { toolInput: { query } } : {}),
  };
}

function mapVaultRowsToDocuments(rows: unknown[]): ActivitySpan["documents"] {
  const documents = [];
  const seen = new Set<string>();
  for (const raw of rows) {
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) continue;
    const h = raw as Record<string, unknown>;
    const meta =
      typeof h.metadata === "object" && h.metadata && !Array.isArray(h.metadata)
        ? (h.metadata as Record<string, unknown>)
        : {};
    const title =
      (typeof h.title === "string" && h.title.trim()) ||
      (typeof meta.title === "string" && meta.title.trim()) ||
      undefined;
    const doc = mapRawSourceToDocument({
      ...h,
      vault_path: h.vault_path ?? h.path ?? h.doc_id,
      snippet:
        h.snippet ??
        (typeof h.body_markdown === "string" ? h.body_markdown.trim().slice(0, 280) : undefined),
      metadata: {
        ...meta,
        ...(title ? { title } : {}),
        vault_path: h.vault_path ?? h.path ?? h.doc_id,
      },
    });
    if (!doc || seen.has(doc.path)) continue;
    seen.add(doc.path);
    documents.push(doc);
  }
  return documents.length ? documents : undefined;
}

function isGetNotePayload(payload: Record<string, unknown>): boolean {
  const tool =
    (typeof payload.tool === "string" && payload.tool.trim()) ||
    (typeof payload.toolName === "string" && payload.toolName.trim()) ||
    "";
  if (tool === DIGIVAULT_GET_NOTE_TOOL) return true;
  if (tool === DIGIVAULT_SEARCH_TOOL) return false;
  // Batch get_note responses use `notes`; search uses `hits`/`results`.
  return payload.notes !== undefined && payload.hits === undefined && payload.results === undefined;
}

/**
 * Map digivault_get_note traces onto ActivitySpan — locate-then-load's second step.
 * digigraph forwards these as `rag_sources` (with `tool: digivault_get_note`) or,
 * for batch/errors, as digivault-native payloads carrying a `notes` array.
 */
export function mapDigivaultGetNote(payload: Record<string, unknown>): ActivitySpan | null {
  const rows = payload.sources ?? payload.notes ?? payload.hits ?? payload.results;
  const query =
    typeof payload.query === "string" && payload.query.trim()
      ? payload.query.trim()
      : undefined;

  if (!Array.isArray(rows)) {
    const errors = payload.errors;
    if (errors && typeof errors === "object" && !Array.isArray(errors)) {
      const paths = Object.keys(errors as Record<string, unknown>);
      if (paths.length > 0) {
        return attachToolArgs(
          {
            operation: "execute_tool",
            status: "failed",
            label: `digivault_get_note errors (${paths.length})`,
            toolName: DIGIVAULT_GET_NOTE_TOOL,
            ...(query ? { query } : {}),
          },
          payload,
        );
      }
    }
    if (payload.status === "started" || payload.status === "in_progress") {
      return attachToolArgs(
        {
          operation: "execute_tool",
          status: "started",
          label: query ? `Loading note: ${query}` : "Loading vault note…",
          toolName: DIGIVAULT_GET_NOTE_TOOL,
          ...(query ? { query } : {}),
        },
        payload,
      );
    }
    return null;
  }

  const documents = mapVaultRowsToDocuments(rows) ?? [];
  const errors =
    payload.errors && typeof payload.errors === "object" && !Array.isArray(payload.errors)
      ? (payload.errors as Record<string, unknown>)
      : undefined;
  const errorCount = errors ? Object.keys(errors).length : 0;
  const path = vaultPathFromPayload(payload, documents);

  if (errorCount > 0 && documents.length === 0) {
    return attachToolArgs(
      {
        operation: "execute_tool",
        status: "failed",
        label: `digivault_get_note errors (${errorCount})`,
        toolName: DIGIVAULT_GET_NOTE_TOOL,
        ...(query ? { query } : {}),
      },
      payload,
    );
  }

  const upstreamHits =
    typeof payload.hit_count === "number" &&
    Number.isFinite(payload.hit_count) &&
    payload.hit_count > 0
      ? Math.trunc(payload.hit_count)
      : undefined;

  return attachToolArgs(
    {
      operation: "retrieve",
      status: "completed",
      label:
        errorCount > 0
          ? `${loadedNoteLabel(path)} (${errorCount} errors)`
          : documents.length > 1
            ? `Loaded ${documents.length} full notes`
            : loadedNoteLabel(path),
      toolName: DIGIVAULT_GET_NOTE_TOOL,
      ...(documents.length ? { documents } : {}),
      ...(!documents.length && upstreamHits ? { hitCount: upstreamHits } : {}),
      ...(query ? { query } : {}),
    },
    payload,
  );
}

/**
 * Map digivault_search_notes digigraph tool/trace payloads onto ActivitySpan.
 * digivault is reached only via digigraph — never as a digichat HTTP backend.
 */
export function mapDigivaultSearchNotes(
  payload: Record<string, unknown>
): ActivitySpan | null {
  if (isGetNotePayload(payload)) {
    return mapDigivaultGetNote(payload);
  }

  const hits = payload.hits ?? payload.results ?? payload.sources;
  const query =
    typeof payload.query === "string" && payload.query.trim()
      ? payload.query.trim()
      : undefined;
  const errorText =
    typeof payload.error === "string" && payload.error.trim() ? payload.error.trim() : "";
  if (payload.status === "failed" || errorText) {
    return attachToolArgs(
      {
        operation: "execute_tool",
        status: "failed",
        label: (errorText || "digivault_search_notes failed").slice(0, 200),
        toolName: DIGIVAULT_SEARCH_TOOL,
        ...(query ? { query } : {}),
      },
      payload,
    );
  }

  if (!Array.isArray(hits)) {
    const errors = payload.errors;
    if (errors && typeof errors === "object" && !Array.isArray(errors)) {
      const paths = Object.keys(errors as Record<string, unknown>);
      if (paths.length > 0) {
        return attachToolArgs(
          {
            operation: "execute_tool",
            status: "failed",
            label: `digivault_search_notes errors (${paths.length})`,
            toolName: DIGIVAULT_SEARCH_TOOL,
            ...(query ? { query } : {}),
          },
          payload,
        );
      }
    }
    if (payload.status === "started" || payload.status === "in_progress") {
      return attachToolArgs(
        {
          operation: "execute_tool",
          status: "started",
          label: "Searching digivault…",
          toolName: DIGIVAULT_SEARCH_TOOL,
          ...(query ? { query } : {}),
        },
        payload,
      );
    }
    return null;
  }

  const documents = mapVaultRowsToDocuments(hits) ?? [];
  const errors =
    payload.errors && typeof payload.errors === "object" && !Array.isArray(payload.errors)
      ? (payload.errors as Record<string, unknown>)
      : undefined;
  const errorCount = errors ? Object.keys(errors).length : 0;
  if (errorCount > 0 && documents.length === 0) {
    return attachToolArgs(
      {
        operation: "execute_tool",
        status: "failed",
        label: `digivault_search_notes errors (${errorCount})`,
        toolName: DIGIVAULT_SEARCH_TOOL,
        ...(query ? { query } : {}),
      },
      payload,
    );
  }
  const upstreamHits =
    typeof payload.hit_count === "number" &&
    Number.isFinite(payload.hit_count) &&
    payload.hit_count > 0
      ? Math.trunc(payload.hit_count)
      : undefined;
  return attachToolArgs(
    {
      operation: "retrieve",
      status: "completed",
      label: errorCount > 0 ? `Sources (${errorCount} errors)` : "Sources",
      toolName: DIGIVAULT_SEARCH_TOOL,
      ...(documents.length ? { documents } : {}),
      ...(!documents.length && upstreamHits ? { hitCount: upstreamHits } : {}),
      ...(query ? { query } : {}),
    },
    payload,
  );
}
