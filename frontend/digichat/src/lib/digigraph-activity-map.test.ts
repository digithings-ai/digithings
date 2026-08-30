import { describe, it, expect } from "vitest";
import { mapDigigraphTraceToSpans } from "./digigraph-activity-map";

describe("mapDigigraphTraceToSpans", () => {
  it("maps rag_sources to retrieve documents with tier/year/snippet", () => {
    const spans = mapDigigraphTraceToSpans(
      {
        type: "rag_sources",
        payload: {
          sources: [
            {
              source_id: "doc-1",
              snippet: "JWT exchange via digikey",
              metadata: {
                title: "Auth plane",
                evidence_tier: "peer_reviewed",
                publication_year: 2024,
              },
            },
            {
              doc_id: "doc-2",
              metadata: { doi_or_arxiv: "10.1/x", peer_reviewed: true },
            },
          ],
        },
      },
      "full"
    );
    expect(spans).toHaveLength(1);
    expect(spans[0]).toMatchObject({
      operation: "retrieve",
      status: "completed",
      label: "Sources",
      toolName: "digisearch",
      documents: [
        {
          title: "Auth plane",
          path: "doc-1",
          tier: "peer_reviewed",
          year: 2024,
          snippet: "JWT exchange via digikey",
        },
        {
          title: "10.1/x",
          path: "doc-2",
          tier: "peer_reviewed",
        },
      ],
    });
    expect(JSON.stringify(spans)).not.toContain("source_id");
  });

  it("maps graph_update research_brief to brief span", () => {
    const spans = mapDigigraphTraceToSpans(
      {
        type: "graph_update",
        payload: {
          research_brief: {
            themes: [{ label: "Auth", summary: "RS256 tokens" }],
          },
          profiling_questions: ["Which tenant?"],
        },
      },
      "full"
    );
    expect(spans).toEqual([
      {
        operation: "chat",
        status: "completed",
        label: "Research brief",
        brief: {
          themes: [{ label: "Auth", summary: "RS256 tokens" }],
          questions: ["Which tenant?"],
        },
      },
    ]);
  });

  it("strips documents and brief at labels", () => {
    const rag = mapDigigraphTraceToSpans(
      {
        type: "rag_sources",
        payload: {
          sources: [{ source_id: "d1", metadata: { title: "T" } }],
        },
      },
      "labels"
    );
    expect(rag[0].documents).toBeUndefined();
    expect(rag[0].documentsWithheld).toBe(true);

    const brief = mapDigigraphTraceToSpans(
      {
        type: "graph_update",
        payload: {
          research_brief: { themes: [{ label: "A", summary: "B" }] },
        },
      },
      "labels"
    );
    expect(brief[0].brief).toBeUndefined();
    expect(brief[0].label).toBe("Research brief");
  });

  it("maps opaque types to chat label spans", () => {
    const spans = mapDigigraphTraceToSpans(
      {
        type: "external_activity",
        payload: { label: "Searching…", status: "completed" },
      },
      "full"
    );
    expect(spans).toEqual([
      { operation: "chat", status: "completed", label: "Searching…" },
    ]);
  });

  it("suppresses bare graph_update LangGraph stream housekeeping", () => {
    expect(
      mapDigigraphTraceToSpans(
        {
          type: "graph_update",
          payload: { update: { research: { keys: ["research_response"] } } },
        },
        "full"
      )
    ).toEqual([]);
    expect(
      mapDigigraphTraceToSpans({ type: "graph_update", payload: {} }, "full")
    ).toEqual([]);
  });

  it("suppresses internal graph_step and span trace types", () => {
    expect(
      mapDigigraphTraceToSpans(
        {
          type: "graph_step",
          payload: { node: "validate_strategy", status: "start" },
        },
        "full"
      )
    ).toEqual([]);
    expect(
      mapDigigraphTraceToSpans(
        { type: "span", payload: { node: "supervisor", depth_remaining: 7 } },
        "full"
      )
    ).toEqual([]);
  });

  it("maps digisearch rag_sources with repo paths and tool label", () => {
    const spans = mapDigigraphTraceToSpans(
      {
        type: "rag_sources",
        payload: {
          tool: "digithings_docs",
          query: "SHOWCASE",
          sources: [
            {
              doc_id: "609e63ae-2671-47ad-bf5a-779ff7d8b757",
              snippet: "# ADR 0001: digithings Project Spec",
              metadata: {
                source_url: "repo://digithings/docs/adr/0001-project-spec.md",
              },
            },
          ],
        },
      },
      "full"
    );
    expect(spans[0]).toMatchObject({
      toolName: "digisearch",
      query: "SHOWCASE",
      documents: [{ path: "docs/adr/0001-project-spec.md", title: "ADR 0001: digithings Project Spec" }],
    });
  });

  it("maps digivault_search_notes hits to Sources", () => {
    const spans = mapDigigraphTraceToSpans(
      {
        type: "digivault_search_notes",
        payload: {
          query: "showcase",
          hits: [
            {
              vault_path: "clients/digithings/digithings-docs-projects-digithings-showcase-md",
              title: "digithings chat — product showcase (client #0)",
              body_markdown: "# digithings chat — product showcase (client #0)",
            },
          ],
        },
      },
      "full"
    );
    expect(spans[0]).toMatchObject({
      label: "Sources",
      toolName: "digivault_search_notes",
      query: "showcase",
      documents: [
        {
          title: "digithings chat — product showcase (client #0)",
          path: "clients/digithings/digithings-docs-projects-digithings-showcase-md",
        },
      ],
    });
  });

  it("emits nothing at off", () => {
    expect(
      mapDigigraphTraceToSpans(
        { type: "rag_sources", payload: { sources: [{ source_id: "d" }] } },
        "off"
      )
    ).toEqual([]);
  });

  // digigraph now emits a rag_sources trace even on a zero-hit search (see
  // digigraph's workflow.py, bb96fb85e) — this must render as a visible span
  // distinct from both a real hit and the tool never having run, not vanish.
  it("maps a zero-hit rag_sources trace to a visible completed retrieve span", () => {
    const spans = mapDigigraphTraceToSpans(
      {
        type: "rag_sources",
        payload: { tool: "digisearch", query: "jwt", sources: [], hit_count: 0 },
      },
      "full"
    );
    expect(spans).toEqual([
      {
        operation: "retrieve",
        status: "completed",
        label: "Sources",
        toolName: "digisearch",
        query: "jwt",
      },
    ]);
  });

  it("maps digivault_get_note rag_sources with a distinct tool name and loaded-path label", () => {
    const spans = mapDigigraphTraceToSpans(
      {
        type: "rag_sources",
        payload: {
          tool: "digivault_get_note",
          query: "clients/digithings/p001",
          sources: [
            {
              doc_id: "clients/digithings/p001",
              metadata: { title: "Page one" },
              snippet: "# Page one",
            },
          ],
        },
      },
      "full",
    );
    expect(spans[0]).toMatchObject({
      toolName: "digivault_get_note",
      label: "Loaded full note: clients/digithings/p001",
      query: "clients/digithings/p001",
    });
  });

  it("maps a zero-hit digivault_search_notes trace to a visible completed retrieve span", () => {
    const spans = mapDigigraphTraceToSpans(
      {
        type: "digivault_search_notes",
        payload: { query: "nonexistent topic", hits: [] },
      },
      "full"
    );
    expect(spans).toEqual([
      {
        operation: "retrieve",
        status: "completed",
        label: "Sources",
        toolName: "digivault_search_notes",
        query: "nonexistent topic",
      },
    ]);
  });
});
