import { createHash } from "node:crypto";

import { MAX_DOC_FIELD_CHARS, MAX_NOTE_BODY_CHARS, type ActivityDocument } from "@/lib/chat-activity";

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** `repo://digithings/docs/foo.md` → `docs/foo.md` for readable Sources rows. */
export function stripRepoPrefix(path: string): string {
  return path.replace(/^repo:\/\/digithings\/?/i, "").replace(/^repo:\/\//i, "").trim();
}

function basename(path: string): string {
  const seg = path.replace(/\\/g, "/").split("/").filter(Boolean).pop();
  return seg ?? path;
}

function titleFromSnippet(snippet: string): string | undefined {
  const line = snippet.split("\n").find((l) => l.trim())?.trim();
  if (!line) return undefined;
  const stripped = line.replace(/^#+\s*/, "").trim();
  return stripped ? stripped.slice(0, MAX_DOC_FIELD_CHARS) : undefined;
}

function isOpaqueId(value: string): boolean {
  const base = value.split("#")[0] ?? value;
  return UUID_RE.test(base);
}

export function resolveSourcePath(
  raw: Record<string, unknown>,
  meta: Record<string, unknown>
): string {
  const candidates = [
    typeof meta.source_url === "string" ? meta.source_url : "",
    typeof meta.path === "string" ? meta.path : "",
    typeof meta.vault_path === "string" ? meta.vault_path : "",
    typeof raw.vault_path === "string" ? raw.vault_path : "",
    typeof raw.doc_id === "string" ? raw.doc_id : "",
    typeof raw.source_id === "string" ? (raw.source_id.split("#")[0] ?? "") : "",
  ]
    .map((s) => s.trim())
    .filter(Boolean);

  for (const c of candidates) {
    const normalized = stripRepoPrefix(c);
    if (normalized && !isOpaqueId(normalized)) {
      return normalized.slice(0, MAX_DOC_FIELD_CHARS);
    }
  }
  const fallback = candidates[0];
  return fallback ? stripRepoPrefix(fallback).slice(0, MAX_DOC_FIELD_CHARS) : "";
}

/**
 * An opaque, stable handle for a document.
 *
 * The handle is what makes the identity of a document stable when the document
 * surfaces more than once — a web URL and a vault path of the same document
 * carry the same handle, a title does not. It is derived from the source's own
 * per-document id and is NOT reversible, because the document id itself must
 * never reach the browser (the activity payload is client facing).
 */
export function documentHandleToken(handle: string): string {
  return `doc-${createHash("sha256").update(handle).digest("hex").slice(0, 16)}`;
}

/**
 * The handle of the document a raw source row describes: the digivault doc id,
 * or the digigraph source id with its chunk rank removed.
 *
 * Both ids are per DOCUMENT: digigraph builds `source_id` as
 * `<doc_id>#<rank>` for a chunk and as `<doc_id>` for a whole document, so the
 * base of the source id is the document id. A DOI is deliberately NOT used
 * here: a DOI names a work, and one work can carry several documents.
 *
 * The handle is carried even when the path was rewritten to the title — that
 * rewrite is exactly the case where the path stops being an identity.
 */
export function resolveDocumentHandle(raw: Record<string, unknown>): string | undefined {
  const docId = (typeof raw.doc_id === "string" ? raw.doc_id : "").split("#")[0]?.trim();
  if (docId) return documentHandleToken(docId);
  const sourceId = (typeof raw.source_id === "string" ? raw.source_id : "")
    .split("#")[0]
    ?.trim();
  if (sourceId) return documentHandleToken(sourceId);
  return undefined;
}

export function resolveSourceTitle(
  path: string,
  meta: Record<string, unknown>,
  snippet?: string
): string {
  const fromMeta =
    (typeof meta.title === "string" && meta.title.trim()) ||
    (typeof meta.doi_or_arxiv === "string" && meta.doi_or_arxiv.trim()) ||
    "";
  if (fromMeta) return fromMeta.slice(0, MAX_DOC_FIELD_CHARS);
  if (snippet) {
    const fromSnip = titleFromSnippet(snippet);
    if (fromSnip) return fromSnip;
  }
  if (path && !isOpaqueId(path)) return basename(path).slice(0, MAX_DOC_FIELD_CHARS);
  return path ? basename(path).slice(0, MAX_DOC_FIELD_CHARS) : "";
}

/** Map digigraph tool ids to short labels shown on Sources tool rows. */
export function ragToolDisplayName(tool: unknown): string {
  const t = typeof tool === "string" ? tool.trim() : "";
  if (!t || t === "rag_sources") return "digisearch";
  if (t === "web_search") return "web_search";
  if (t === "digivault_search_notes") return "digivault_search_notes";
  if (t === "digivault_get_note") return "digivault_get_note";
  if (t === "digivault") return "digivault";
  // Keep dedicated per-index tools (digisearch_occ_help, digisearch_zammad_tickets,
  // DIG-3269) under their real name: the started row is keyed by that name, so
  // collapsing the completion to "digisearch" spawned a second, generic row.
  if (t === "digithings_docs") return "digisearch";
  return t.slice(0, MAX_DOC_FIELD_CHARS);
}

export function mapRawSourceToDocument(raw: Record<string, unknown>): ActivityDocument | null {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  const meta =
    raw.metadata && typeof raw.metadata === "object" && !Array.isArray(raw.metadata)
      ? (raw.metadata as Record<string, unknown>)
      : {};
  const snippet =
    typeof raw.snippet === "string" && raw.snippet.trim()
      ? raw.snippet.trim().slice(0, 280)
      : undefined;
  const pathRaw = resolveSourcePath(raw, meta);
  const title = resolveSourceTitle(pathRaw, meta, snippet);
  let path = pathRaw;
  if (path && isOpaqueId(path) && title) {
    // No repo path in metadata — show the heading only, not a bare UUID path.
    path = title;
  }
  if (!path || !title) return null;
  const doc: ActivityDocument = { title, path };
  const handle = resolveDocumentHandle(raw);
  if (handle) doc.docId = handle;
  const tier =
    (typeof meta.evidence_tier === "string" && meta.evidence_tier.trim()) ||
    (meta.source_kind === "external" ? "External" : undefined) ||
    (meta.peer_reviewed === true ? "peer_reviewed" : undefined);
  if (tier) doc.tier = tier;
  if (typeof meta.publication_year === "number" && Number.isFinite(meta.publication_year)) {
    doc.year = Math.trunc(meta.publication_year);
  }
  if (snippet) doc.snippet = snippet;
  const bodyRaw =
    (typeof raw.body === "string" && raw.body.trim()) ||
    (typeof raw.body_markdown === "string" && raw.body_markdown.trim()) ||
    "";
  if (bodyRaw) doc.body = bodyRaw.slice(0, MAX_NOTE_BODY_CHARS);
  return doc;
}
