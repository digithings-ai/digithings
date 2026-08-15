import { describe, expect, it } from "vitest";
import { mapDigivaultSearchNotes } from "./digivault";

describe("mapDigivaultSearchNotes", () => {
  it("maps a zero-hit search-notes trace to a completed retrieve span with no documents", () => {
    // Same defect as mapDigisearchRagSources: an empty `hits` array is a real
    // completed search that found nothing, not "never searched".
    const span = mapDigivaultSearchNotes({ query: "nonexistent topic", hits: [] });

    expect(span).toEqual({
      operation: "retrieve",
      status: "completed",
      label: "Sources",
      toolName: "digivault",
      query: "nonexistent topic",
    });
    expect(span).not.toHaveProperty("documents");
  });

  it("omits query when the zero-hit trace carries none", () => {
    expect(mapDigivaultSearchNotes({ hits: [] })).toEqual({
      operation: "retrieve",
      status: "completed",
      label: "Sources",
      toolName: "digivault",
    });
  });

  it("still renders the in-flight 'Searching digivault…' span when hits is absent and status is started", () => {
    expect(mapDigivaultSearchNotes({ query: "showcase", status: "started" })).toEqual({
      operation: "execute_tool",
      status: "started",
      label: "Searching digivault…",
      toolName: "digivault",
      query: "showcase",
    });
  });

  it("still returns null when hits/results/notes and status are all absent", () => {
    expect(mapDigivaultSearchNotes({ query: "showcase" })).toBeNull();
  });

  it("preserves digivault_get_note batch errors when notes are absent", () => {
    expect(
      mapDigivaultSearchNotes({
        query: "batch",
        errors: {
          "clients/x/missing": "not found",
          "clients/x/bad": "forbidden",
        },
      }),
    ).toEqual({
      operation: "execute_tool",
      status: "failed",
      label: "digivault errors (2)",
      toolName: "digivault",
      query: "batch",
    });
  });

  it("keeps successful batch notes alongside partial errors", () => {
    const span = mapDigivaultSearchNotes({
      notes: [
        {
          vault_path: "clients/digithings/ok",
          title: "OK",
          body_markdown: "body",
        },
      ],
      errors: { "clients/digithings/missing": "not found" },
      query: "batch",
    });
    expect(span?.status).toBe("completed");
    expect(span?.label).toBe("Sources (1 errors)");
    expect(span?.documents).toEqual([
      { title: "OK", path: "clients/digithings/ok", snippet: "body" },
    ]);
  });

  it("maps notes:[] with only errors as execute_tool failed (not a fake hitCount)", () => {
    expect(
      mapDigivaultSearchNotes({
        notes: [],
        errors: { "clients/x/missing": "not found" },
        query: "batch",
      }),
    ).toEqual({
      operation: "execute_tool",
      status: "failed",
      label: "digivault errors (1)",
      toolName: "digivault",
      query: "batch",
    });
  });

  it("leaves the successful (non-empty) path byte-identical", () => {
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
      toolName: "digivault",
      documents: [
        {
          title: "digithings chat — product showcase (client #0)",
          path: "clients/digithings/digithings-docs-projects-digithings-showcase-md",
          snippet: "# digithings chat — product showcase (client #0)",
        },
      ],
      query: "showcase",
    });
  });
});
