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
              snippet: "JWT exchange via DigiKey",
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
      toolName: "rag_sources",
      documents: [
        {
          title: "Auth plane",
          path: "doc-1",
          tier: "peer_reviewed",
          year: 2024,
          snippet: "JWT exchange via DigiKey",
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

  it("emits nothing at off", () => {
    expect(
      mapDigigraphTraceToSpans(
        { type: "rag_sources", payload: { sources: [{ source_id: "d" }] } },
        "off"
      )
    ).toEqual([]);
  });
});
