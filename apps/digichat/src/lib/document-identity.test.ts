import { describe, expect, it } from "vitest";
import type { ActivityDocument } from "@/lib/chat-activity";
import { activityDocumentKind, documentIdentityKeys, sameActivityDocument } from "./document-identity";

function doc(over: Partial<ActivityDocument> = {}): ActivityDocument {
  return { title: "A note", path: "docs/a-note.md", ...over };
}

describe("documentIdentityKeys", () => {
  it("uses the source handle as an identity key", () => {
    const keys = documentIdentityKeys(
      doc({ docId: "609e63ae-2671-47ad-bf5a-779ff7d8b757" })
    );
    expect(keys).toContain("doc:609e63ae-2671-47ad-bf5a-779ff7d8b757");
  });

  it("uses a real path as an identity key", () => {
    expect(documentIdentityKeys(doc({ path: "docs/a-note.md" }))).toContain(
      "path:docs/a-note.md"
    );
  });

  it("treats a path that repeats the title as a label, not a location", () => {
    // Producers substitute the title for the path when the source has no
    // usable path — that is a label, it must not identify anything.
    const keys = documentIdentityKeys(doc({ title: "A note", path: "A note" }));
    expect(keys.some((key) => key.startsWith("path:"))).toBe(false);
    expect(keys).toEqual(["title:a note|kind:document"]);
  });

  it("falls back to title plus kind when there is no handle and no location", () => {
    const keys = documentIdentityKeys(
      doc({ title: "https://example.com/a", path: "https://example.com/a" })
    );
    expect(keys).toEqual(["title:https://example.com/a|kind:web"]);
  });

  it("does not key a title-only document by its title when it also has a location", () => {
    const keys = documentIdentityKeys(doc({ title: "A note", path: "docs/a-note.md" }));
    expect(keys.some((key) => key.startsWith("title:"))).toBe(false);
  });

  it("normalises case and surrounding whitespace", () => {
    expect(documentIdentityKeys(doc({ title: " A NOTE ", path: " DOCS/A-Note.md " }))).toEqual([
      "path:docs/a-note.md",
    ]);
  });

  it("returns no keys for a document that carries no identity at all", () => {
    expect(documentIdentityKeys({ title: "", path: "" })).toEqual([]);
  });
});

describe("activityDocumentKind", () => {
  it("reads a web document from its http(s) path", () => {
    expect(activityDocumentKind(doc({ path: "https://example.com/a" }))).toBe("web");
    expect(activityDocumentKind(doc({ path: "docs/a.md" }))).toBe("document");
  });
});

describe("sameActivityDocument", () => {
  it("does not merge two documents that only share a title", () => {
    const a = doc({ title: "Shared title", path: "docs/one.md" });
    const b = doc({ title: "Shared title", path: "docs/two.md" });
    expect(sameActivityDocument(a, b)).toBe(false);
  });

  it("merges one document that surfaces as a web URL and as a vault path", () => {
    const asWeb = doc({ title: "Auth doc", path: "https://example.com/auth", docId: "doc-1" });
    const asVault = doc({ title: "Auth doc", path: "vault/auth.md", docId: "doc-1" });
    expect(sameActivityDocument(asWeb, asVault)).toBe(true);
  });

  it("merges the same location reported under two different handles", () => {
    const a = doc({ title: "Auth doc", path: "vault/auth.md", docId: "doc-1" });
    const b = doc({ title: "Auth doc", path: "vault/auth.md", docId: "doc-2" });
    expect(sameActivityDocument(a, b)).toBe(true);
  });

  it("does not merge two different documents that carry different handles", () => {
    const a = doc({ title: "Shared title", path: "Shared title", docId: "doc-1" });
    const b = doc({ title: "Shared title", path: "Shared title", docId: "doc-2" });
    expect(sameActivityDocument(a, b)).toBe(false);
  });

  it("does not merge a title-only document into a located document with the same title", () => {
    const titleOnly = doc({ title: "Shared title", path: "Shared title" });
    const located = doc({ title: "Shared title", path: "docs/shared.md" });
    expect(sameActivityDocument(titleOnly, located)).toBe(false);
  });
});
