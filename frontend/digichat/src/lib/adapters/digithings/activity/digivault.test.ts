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
