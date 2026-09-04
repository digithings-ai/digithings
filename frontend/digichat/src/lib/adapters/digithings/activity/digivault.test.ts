import { describe, expect, it } from "vitest";
import { mapDigivaultGetNote, mapDigivaultSearchNotes } from "./digivault";

describe("mapDigivaultSearchNotes", () => {
  it("maps a zero-hit search-notes trace to a completed retrieve span with no documents", () => {
    const span = mapDigivaultSearchNotes({ query: "nonexistent topic", hits: [] });

    expect(span).toEqual({
      operation: "retrieve",
      status: "completed",
      label: "Sources",
      toolName: "digivault_search_notes",
      query: "nonexistent topic",
    });
    expect(span).not.toHaveProperty("documents");
  });

  it("omits query when the zero-hit trace carries none", () => {
    expect(mapDigivaultSearchNotes({ hits: [] })).toEqual({
      operation: "retrieve",
      status: "completed",
      label: "Sources",
      toolName: "digivault_search_notes",
    });
  });

  it("still renders the in-flight 'Searching digivault…' span when hits is absent and status is started", () => {
    expect(mapDigivaultSearchNotes({ query: "showcase", status: "started" })).toEqual({
      operation: "execute_tool",
      status: "started",
      label: "Searching digivault…",
      toolName: "digivault_search_notes",
      query: "showcase",
    });
  });

  it("still returns null when hits/results/notes and status are all absent", () => {
    expect(mapDigivaultSearchNotes({ query: "showcase" })).toBeNull();
  });

  it("routes batch note payloads through mapDigivaultGetNote", () => {
    expect(
      mapDigivaultSearchNotes({
        notes: [],
        errors: { "clients/x/missing": "not found" },
        query: "batch",
      }),
    ).toEqual({
      operation: "execute_tool",
      status: "failed",
      label: "digivault_get_note errors (1)",
      toolName: "digivault_get_note",
      query: "batch",
    });
  });

  it("leaves the successful search path unchanged apart from toolName", () => {
    const payload = {
      query: "showcase",
      hits: [
        {
          vault_path: "clients/digithings/digithings-docs-projects-digithings-showcase-md",
          title: "digithings chat — product showcase (client #0)",
          body_markdown: "# digithings chat — product showcase (client #0)",
        },
      ],
    };
    expect(mapDigivaultSearchNotes(payload)).toEqual({
      operation: "retrieve",
      status: "completed",
      label: "Sources",
      toolName: "digivault_search_notes",
      documents: [
        {
          title: "digithings chat — product showcase (client #0)",
          path: "clients/digithings/digithings-docs-projects-digithings-showcase-md",
          snippet: "# digithings chat — product showcase (client #0)",
          body: "# digithings chat — product showcase (client #0)",
        },
      ],
      query: "showcase",
    });
  });
});

describe("mapDigivaultGetNote", () => {
  it("preserves batch errors when notes are absent", () => {
    expect(
      mapDigivaultGetNote({
        query: "batch",
        errors: {
          "clients/x/missing": "not found",
          "clients/x/bad": "forbidden",
        },
      }),
    ).toEqual({
      operation: "execute_tool",
      status: "failed",
      label: "digivault_get_note errors (2)",
      toolName: "digivault_get_note",
      query: "batch",
    });
  });

  it("keeps successful batch notes alongside partial errors", () => {
    const span = mapDigivaultGetNote({
      notes: [
        {
          vault_path: "clients/digithings/ok",
          title: "OK",
          body_markdown: "body",
        },
      ],
      errors: { "clients/digithings/missing": "not found" },
      query: "clients/digithings/ok",
    });
    expect(span).toMatchObject({
      status: "completed",
      toolName: "digivault_get_note",
      label: "Loaded full note: clients/digithings/ok (1 errors)",
      query: "clients/digithings/ok",
    });
    expect(span?.documents).toEqual([
      { title: "OK", path: "clients/digithings/ok", snippet: "body", body: "body" },
    ]);
  });

  it("maps rag_sources get_note traces with a loaded-path label", () => {
    const span = mapDigivaultGetNote({
      tool: "digivault_get_note",
      query: "clients/digithings/p001",
      sources: [
        {
          doc_id: "clients/digithings/p001",
          metadata: { title: "Page one" },
          snippet: "# Page one",
        },
      ],
    });
    expect(span).toMatchObject({
      toolName: "digivault_get_note",
      label: "Loaded full note: clients/digithings/p001",
      query: "clients/digithings/p001",
    });
  });
});
