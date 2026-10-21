import type { ActivityDocument } from "@/lib/chat-activity";

/**
 * Identity of an activity document (one row of the Sources list).
 *
 * Two failure modes have to be avoided at the same time:
 *
 *  - two DIFFERENT documents that merely share a title must not collapse into
 *    one — the second one was silently dropped from the Sources list;
 *  - ONE document that reaches us through two surfaces (a web URL and a vault
 *    path) must not be written twice — that duplicate is what the source-level
 *    dedupe exists to remove.
 *
 * A path is not enough to answer either question: a path names a LOCATION, not a
 * document, and one document can have more than one location. A document is
 * therefore identified by the SET of keys it carries, and two documents are the
 * same document when their key sets intersect.
 *
 * Keys, in the order they are considered:
 *
 *  - `doc:<handle>` — the source's own stable handle for the document
 *    (`ActivityDocument.docId`). It outranks the path because it is the only key
 *    every surface of one document shares. Producers that expose no handle
 *    simply do not carry this key.
 *  - `path:<path>` — a real LOCATION. A path that merely repeats the title is a
 *    LABEL (producers substitute the title for the path when the source has no
 *    usable path), so it never identifies anything.
 *  - `title:<title>|kind:<kind>` — the fallback for a document that carries
 *    neither a handle nor a location. `kind` is the rendered source kind, so
 *    that a title-only web document and a title-only vault document do not
 *    collapse into each other.
 *
 * Every key is normalised with trim + lower case.
 */

const HTTP_URL_RE = /^https?:\/\//i;

/** The rendered kind of a document: a link to a page, or a document to open. */
export type ActivityDocumentKind = "web" | "document";

/** True when the path is an http(s) URL — the shape rendered as a link. */
export function isWebLocation(path: string): boolean {
  return HTTP_URL_RE.test(path);
}

function normalizeKeyPart(value: string | undefined): string {
  return (value ?? "").trim().toLowerCase();
}

/** The rendered kind of a document. */
export function activityDocumentKind(doc: ActivityDocument): ActivityDocumentKind {
  return isWebLocation(doc.path) ? "web" : "document";
}

/**
 * The identity keys of a document. An empty list means the document carries no
 * identity at all (no handle, no location and no title) — such a document is
 * never treated as a duplicate of anything.
 */
export function documentIdentityKeys(doc: ActivityDocument): string[] {
  const handle = normalizeKeyPart(doc.docId);
  const path = normalizeKeyPart(doc.path);
  const title = normalizeKeyPart(doc.title);
  const keys: string[] = [];

  if (handle) keys.push(`doc:${handle}`);
  // A path that repeats the title is a label, not a location.
  if (path && path !== title) keys.push(`path:${path}`);
  if (keys.length === 0 && title) {
    keys.push(`title:${title}|kind:${activityDocumentKind(doc)}`);
  }
  return keys;
}

/** True when two documents are the same document (their key sets intersect). */
export function sameActivityDocument(a: ActivityDocument, b: ActivityDocument): boolean {
  const other = new Set(documentIdentityKeys(b));
  return documentIdentityKeys(a).some((key) => other.has(key));
}
