import { describe, it, expect } from "vitest";
import type { UIMessage } from "ai";
import {
  sanitizeActivitySpan,
  applyActivityDetail,
  toDigiChatActivity,
  messageActivities,
  ACTIVITY_PART_TYPE,
  MAX_LABEL_CHARS,
  MAX_DOCUMENTS,
  MAX_SNIPPET_CHARS,
  MAX_BRIEF_THEMES,
  MAX_BRIEF_QUESTIONS,
  type ActivitySpan,
} from "./chat-activity";

const span = (extra: Record<string, unknown> = {}): Record<string, unknown> => ({
  operation: "execute_tool",
  status: "started",
  label: "Searching knowledge base…",
  ...extra,
});

describe("sanitizeActivitySpan", () => {
  it("keeps every declared field", () => {
    expect(
      sanitizeActivitySpan(
        span({
          status: "completed",
          operation: "retrieve",
          toolName: "file_search",
          query: "auth",
          documents: [{ title: "Auth", path: "https://x/auth" }],
          reasoningDelta: "thinking",
        })
      )
    ).toEqual({
      operation: "retrieve",
      status: "completed",
      label: "Searching knowledge base…",
      toolName: "file_search",
      query: "auth",
      documents: [{ title: "Auth", path: "https://x/auth" }],
      reasoningDelta: "thinking",
    });
  });

  // The disclosure boundary: this type IS the allowlist, so anything a provider
  // did not mean to publish must not survive projection onto the public embed.
  it("drops undeclared keys rather than passing them through", () => {
    const out = sanitizeActivitySpan(
      span({
        projectEndpoint: "https://internal.foundry.azure.com",
        "gen_ai.request.model": "gpt-4o",
        prompt: "the user's private question",
        upstreamError: "Traceback (most recent call last)…",
      })
    );
    expect(out).not.toBeNull();
    expect(Object.keys(out!).sort()).toEqual(["label", "operation", "status"]);
  });

  it("rejects an unknown operation or status", () => {
    expect(sanitizeActivitySpan(span({ operation: "exfiltrate" }))).toBeNull();
    expect(sanitizeActivitySpan(span({ status: "maybe" }))).toBeNull();
  });

  it("rejects non-object input", () => {
    expect(sanitizeActivitySpan(null)).toBeNull();
    expect(sanitizeActivitySpan("started")).toBeNull();
    expect(sanitizeActivitySpan([span()])).toBeNull();
  });

  it("truncates an over-long label and caps the document list", () => {
    const out = sanitizeActivitySpan(
      span({
        label: "x".repeat(MAX_LABEL_CHARS + 50),
        documents: Array.from({ length: MAX_DOCUMENTS + 5 }, (_, i) => ({
          title: `t${i}`,
          path: `p${i}`,
        })),
      })
    );
    expect(out!.label).toHaveLength(MAX_LABEL_CHARS);
    expect(out!.documents).toHaveLength(MAX_DOCUMENTS);
  });

  it("drops malformed documents without dropping the span", () => {
    const out = sanitizeActivitySpan(
      span({ documents: [{ title: "ok", path: "p" }, { title: 42 }, null, "nope"] })
    );
    expect(out!.documents).toEqual([{ title: "ok", path: "p" }]);
  });

  it("omits documents entirely when none survive", () => {
    const out = sanitizeActivitySpan(span({ documents: [null, "nope"] }));
    expect(out).not.toBeNull();
    expect("documents" in out!).toBe(false);
  });

  // documentsWithheld is a derived boolean applyActivityDetail sets, not
  // upstream data — but it still has to round-trip once the client re-parses
  // the span off the wire, so the allowlist must carry it.
  it("keeps documentsWithheld when true but drops it when absent or false", () => {
    expect(sanitizeActivitySpan(span({ documentsWithheld: true }))?.documentsWithheld).toBe(true);
    expect(sanitizeActivitySpan(span({ documentsWithheld: false }))).not.toHaveProperty(
      "documentsWithheld"
    );
    expect(sanitizeActivitySpan(span({ documentsWithheld: "true" }))).not.toHaveProperty(
      "documentsWithheld"
    );
  });
});

describe("applyActivityDetail", () => {
  const full: ActivitySpan = {
    operation: "retrieve",
    status: "completed",
    label: "Sources",
    toolName: "file_search",
    query: "auth",
    documents: [{ title: "Auth", path: "https://x/auth" }],
    reasoningDelta: "thinking",
  };

  it("emits nothing at all when detail is off", () => {
    expect(applyActivityDetail(full, "off")).toBeNull();
  });

  // Server-side gate: "labels" tenants must never receive documents over the
  // wire. This is not CSS hiding.
  it("strips documents and reasoning at labels", () => {
    const out = applyActivityDetail(full, "labels")!;
    expect(out.documents).toBeUndefined();
    expect(out.reasoningDelta).toBeUndefined();
    expect(out.label).toBe("Sources");
    expect(out.query).toBe("auth");
  });

  // The signal the projector needs to tell "results withheld" apart from
  // "genuinely no results" (see toDigiChatActivity below).
  it("flags documentsWithheld at labels only when real documents were stripped", () => {
    expect(applyActivityDetail(full, "labels")!.documentsWithheld).toBe(true);
    const noDocs: ActivitySpan = { ...full, documents: undefined };
    expect(applyActivityDetail(noDocs, "labels")!.documentsWithheld).toBeUndefined();
    const emptyDocs: ActivitySpan = { ...full, documents: [] };
    expect(applyActivityDetail(emptyDocs, "labels")!.documentsWithheld).toBeUndefined();
  });

  it("passes everything through at full", () => {
    expect(applyActivityDetail(full, "full")).toEqual(full);
  });

  // Full detail must stay byte-for-byte unaffected by the new flag's plumbing.
  it("never sets documentsWithheld at full", () => {
    expect(applyActivityDetail(full, "full")!.documentsWithheld).toBeUndefined();
  });
});

const started = (toolName: string, query?: string): ActivitySpan => ({
  operation: "execute_tool",
  toolName,
  status: "started",
  label: "Searching knowledge base…",
  ...(query ? { query } : {}),
});

const finished = (toolName: string, query: string): ActivitySpan => ({
  operation: "execute_tool",
  toolName,
  query,
  status: "completed",
  label: `Searched for: "${query}"`,
});

const retrieved = (
  toolName: string,
  query: string,
  docs: { title: string; path: string }[]
): ActivitySpan => ({
  operation: "retrieve",
  toolName,
  query,
  status: "completed",
  label: "Sources",
  documents: docs,
});

describe("toDigiChatActivity", () => {
  it("returns no rows for no spans", () => {
    expect(toDigiChatActivity([])).toEqual([]);
  });

  // The Foundry shape: three spans across two events collapse to one result row.
  it("merges the search and its citations into a single tool_result", () => {
    const rows = toDigiChatActivity([
      started("file_search"),
      finished("file_search", "auth"),
      retrieved("file_search", "auth", [{ title: "Auth", path: "https://x/auth" }]),
    ]);
    expect(rows).toEqual([
      {
        kind: "tool_result",
        name: "file_search",
        query: "auth",
        hits: [{ title: "Auth", path: "https://x/auth" }],
        count: 1,
      },
    ]);
  });

  // CodeRabbit finding (#2327 review): merging two hitCount-only retrieve spans
  // (both with empty `hits`, e.g. digivault_get_note rounds whose citations
  // don't carry structured hits) unconditionally set count: mergedHits.length,
  // silently dropping a genuinely positive count to 0 — the exact "no hits"
  // misreport the surrounding documentsWithheld logic exists to prevent.
  it("keeps a positive hitCount-derived count when merging two hits-less retrieve spans", () => {
    const withHitCount = (toolName: string, query: string, hitCount: number): ActivitySpan => ({
      operation: "retrieve",
      toolName,
      query,
      status: "completed",
      label: "Sources",
      hitCount,
    });
    const rows = toDigiChatActivity([
      withHitCount("digivault_get_note", "clients/x/p001", 1),
      withHitCount("digivault_get_note", "clients/x/p001", 1),
    ]);
    expect(rows).toEqual([
      { kind: "tool_result", name: "digivault_get_note", query: "clients/x/p001", hits: [], count: 1 },
    ]);
  });

  it("still prefers mergedHits.length over hitCount once real hits are present", () => {
    const rows = toDigiChatActivity([
      retrieved("digivault_search_notes", "q", [{ title: "A", path: "a" }]),
      retrieved("digivault_search_notes", "q", [{ title: "B", path: "b" }]),
    ]);
    expect(rows).toEqual([
      {
        kind: "tool_result",
        name: "digivault_search_notes",
        query: "q",
        hits: [
          { title: "A", path: "a" },
          { title: "B", path: "b" },
        ],
        count: 2,
      },
    ]);
  });

  it("renders an in-flight search as a tool_call", () => {
    expect(toDigiChatActivity([started("file_search")])).toEqual([
      { kind: "tool_call", name: "file_search", query: "" },
    ]);
  });

  it("renders a completed search with no citations as a no-hits result", () => {
    expect(toDigiChatActivity([started("file_search"), finished("file_search", "auth")])).toEqual([
      { kind: "tool_result", name: "file_search", query: "auth", hits: [], count: 0 },
    ]);
  });

  // digisearch/digivault (via digigraph) never emit a preceding execute_tool
  // started/completed pair — a zero-hit search reaches here as a single
  // completed `retrieve` span with no `documents` field (see
  // mapDigisearchRagSources/mapDigivaultSearchNotes). It must render the same
  // honest "no hits" result as the settle-pass case above, distinct from both
  // a real hit (has documents) and the tool never running (no span at all).
  it("renders a lone zero-hit retrieve span (no preceding execute_tool) as a no-hits result", () => {
    expect(
      toDigiChatActivity([
        { operation: "retrieve", toolName: "digisearch", query: "jwt", status: "completed", label: "Sources" },
      ])
    ).toEqual([{ kind: "tool_result", name: "digisearch", query: "jwt", hits: [], count: 0 }]);
  });

  it("keeps a completed search as a running tool_call until the turn settles", () => {
    expect(
      toDigiChatActivity([started("file_search"), finished("file_search", "auth")], {
        settle: false,
      }),
    ).toEqual([{ kind: "tool_call", name: "file_search", query: "auth" }]);
  });

  it("still settles a failed search mid-stream", () => {
    expect(
      toDigiChatActivity(
        [
          started("file_search"),
          { ...finished("file_search", "auth"), status: "failed" },
        ],
        { settle: false },
      ),
    ).toEqual([{ kind: "status", message: 'Search for "auth" failed.' }]);
  });

  it("keeps two different queries as separate rows", () => {
    const rows = toDigiChatActivity([
      finished("file_search", "auth"),
      retrieved("file_search", "auth", [{ title: "A", path: "a" }]),
      finished("file_search", "billing"),
      retrieved("file_search", "billing", [{ title: "B", path: "b" }]),
    ]);
    expect(rows).toHaveLength(2);
    expect(rows.map((r) => (r.kind === "tool_result" ? r.query : null))).toEqual([
      "auth",
      "billing",
    ]);
  });

  it("collapses repeated chat traces by label and ORs their done flag", () => {
    const trace = (label: string, status: ActivitySpan["status"]): ActivitySpan => ({
      operation: "chat",
      status,
      label,
    });
    expect(
      toDigiChatActivity([trace("Planning", "started"), trace("Planning", "completed")])
    ).toEqual([{ kind: "trace", label: "Planning", done: true }]);
  });

  it("accumulates reasoning deltas into one trailing block", () => {
    const reason = (text: string): ActivitySpan => ({
      operation: "chat",
      status: "started",
      label: "reasoning",
      reasoningDelta: text,
    });
    expect(toDigiChatActivity([reason("one "), reason("two")])).toEqual([
      { kind: "reasoning", text: "one two" },
    ]);
  });

  // "failed" is terminal: the row must settle, not spin forever.
  it("settles a failed step rather than leaving it pending", () => {
    expect(
      toDigiChatActivity([{ operation: "chat", status: "failed", label: "Planning" }])
    ).toEqual([{ kind: "trace", label: "Planning", done: true }]);
  });

  // A failed search is neither "still running" nor "ran and found nothing" —
  // rendering it as a zero-count tool_result (the no-hits case) would tell the
  // user the search completed successfully. Regression: this exact case used
  // to fall through to the no-hits branch because "completed" and "failed"
  // were tracked identically.
  it("renders a failed search as an honest failure, not a fabricated no-hits result", () => {
    expect(
      toDigiChatActivity([
        started("file_search"),
        { ...finished("file_search", "auth"), status: "failed" },
      ])
    ).toEqual([{ kind: "status", message: 'Search for "auth" failed.' }]);
  });

  it("renders a failed search with no known query using a generic message", () => {
    expect(
      toDigiChatActivity([{ operation: "execute_tool", toolName: "file_search", status: "failed", label: "x" }])
    ).toEqual([{ kind: "status", message: "Search failed." }]);
  });

  // Regression (#2330): a failed retrieve with hitCount set (error count
  // mistakenly reused as hit_count) must not render as N successful hits.
  it("renders a failed retrieve span as a failure, never as hitCount successes", () => {
    expect(
      toDigiChatActivity([
        {
          operation: "retrieve",
          status: "failed",
          label: "digivault errors (2)",
          toolName: "digivault_search_notes",
          query: "batch",
          hitCount: 2,
        },
      ]),
    ).toEqual([{ kind: "status", message: 'Search for "batch" failed.' }]);
  });

  it("still uses positive hitCount on a completed retrieve when documents mapped empty", () => {
    expect(
      toDigiChatActivity([
        {
          operation: "retrieve",
          status: "completed",
          label: "Sources",
          toolName: "digisearch",
          query: "jwt",
          hitCount: 3,
        },
      ]),
    ).toEqual([{ kind: "tool_result", name: "digisearch", query: "jwt", hits: [], count: 3 }]);
  });

  it("renders citations with no preceding search step using an empty query", () => {
    expect(
      toDigiChatActivity([
        { operation: "retrieve", status: "completed", label: "Sources", documents: [{ title: "A", path: "a" }] },
      ])
    ).toEqual([{ kind: "tool_result", name: "search", query: "", hits: [{ title: "A", path: "a" }], count: 1 }]);
  });

  // Regression: a repeated search for the same (toolName, query) must collapse
  // onto its one existing row, not leave a second "started" placeholder behind
  // once the blank-key slot it opened in is later reused by a fresh call.
  it("does not leave a phantom tool_call row when the same search runs twice in a row", () => {
    const rows = toDigiChatActivity([
      started("file_search"),
      finished("file_search", "auth"),
      started("file_search"),
      finished("file_search", "auth"),
      retrieved("file_search", "auth", [{ title: "Auth", path: "https://x/auth" }]),
    ]);
    expect(rows).toEqual([
      {
        kind: "tool_result",
        name: "file_search",
        query: "auth",
        hits: [{ title: "Auth", path: "https://x/auth" }],
        count: 1,
      },
    ]);
  });

  // Guard against an over-eager fix: two genuinely different queries, each
  // announced by its own "started" span, must still stay two separate rows.
  it("keeps two different queries separate even when each is preceded by its own started span", () => {
    const rows = toDigiChatActivity([
      started("file_search"),
      finished("file_search", "auth"),
      retrieved("file_search", "auth", [{ title: "A", path: "a" }]),
      started("file_search"),
      finished("file_search", "billing"),
      retrieved("file_search", "billing", [{ title: "B", path: "b" }]),
    ]);
    expect(rows).toHaveLength(2);
    expect(rows.map((r) => (r.kind === "tool_result" ? r.query : null))).toEqual([
      "auth",
      "billing",
    ]);
  });

  // Regression: a `retrieve` span following a `started` span with no
  // intervening execute_tool completion — exactly the shape
  // adapters/foundry/stream.test.ts's own `searchEvents` fixture produces (Foundry
  // citations arrive straight off the message, with no file_search_call
  // output_item.done in between) — must resolve the pending placeholder
  // rather than leave it as an orphaned, never-settling tool_call row.
  it("resolves a still-open started row directly from retrieve when no execute_tool completion arrives", () => {
    const rows = toDigiChatActivity([
      started("file_search"),
      {
        operation: "retrieve",
        toolName: "file_search",
        status: "completed",
        label: "Sources",
        documents: [{ title: "Auth", path: "https://x/auth" }],
      },
    ]);
    expect(rows).toEqual([
      {
        kind: "tool_result",
        name: "file_search",
        query: "",
        hits: [{ title: "Auth", path: "https://x/auth" }],
        count: 1,
      },
    ]);
  });
});

describe("toDigiChatActivity — documentsWithheld (labels detail)", () => {
  // The bug: a `labels` tenant stripped of documents by applyActivityDetail
  // must not have a real search result rendered as the literal "no hits"
  // string the shared UI produces for count === 0.
  it("renders an honest status row instead of a fabricated no-hits result when documents were withheld", () => {
    const rows = toDigiChatActivity([
      started("file_search"),
      finished("file_search", "auth"),
      {
        operation: "retrieve",
        toolName: "file_search",
        query: "auth",
        status: "completed",
        label: "Sources",
        documentsWithheld: true,
      },
    ]);
    expect(rows).toEqual([{ kind: "status", message: 'Found results for "auth".' }]);
    expect(rows).not.toContainEqual(expect.objectContaining({ kind: "tool_result", count: 0 }));
  });

  // A genuinely empty search never produces a retrieve span at all (no
  // provider emits one with zero documents), so it must still fall through
  // to the existing trailing no-hits pass and read sensibly.
  it("still renders a sensible no-hits result for a genuinely empty search", () => {
    const rows = toDigiChatActivity([started("file_search"), finished("file_search", "auth")]);
    expect(rows).toEqual([
      { kind: "tool_result", name: "file_search", query: "auth", hits: [], count: 0 },
    ]);
  });

  it("leaves full detail unchanged: a retrieve span without documentsWithheld renders the real hits and count", () => {
    const rows = toDigiChatActivity([
      started("file_search"),
      finished("file_search", "auth"),
      retrieved("file_search", "auth", [{ title: "Auth", path: "https://x/auth" }]),
    ]);
    expect(rows).toEqual([
      {
        kind: "tool_result",
        name: "file_search",
        query: "auth",
        hits: [{ title: "Auth", path: "https://x/auth" }],
        count: 1,
      },
    ]);
  });
});

describe("Phase 2 document fields + brief allowlist", () => {
  it("keeps tier, year, snippet on documents and drops undeclared doc keys", () => {
    const out = sanitizeActivitySpan(
      span({
        operation: "retrieve",
        status: "completed",
        documents: [
          {
            title: "Auth",
            path: "https://x/auth",
            tier: "peer_reviewed",
            year: 2024,
            snippet: "hello",
            source_id: "leak",
            score: 0.99,
            body_markdown: "# secret",
          },
        ],
      }),
    );
    expect(out!.documents).toEqual([
      {
        title: "Auth",
        path: "https://x/auth",
        tier: "peer_reviewed",
        year: 2024,
        snippet: "hello",
      },
    ]);
  });

  it("caps snippet length", () => {
    const out = sanitizeActivitySpan(
      span({
        operation: "retrieve",
        status: "completed",
        documents: [
          {
            title: "T",
            path: "p",
            snippet: "s".repeat(MAX_SNIPPET_CHARS + 40),
          },
        ],
      }),
    );
    expect(out!.documents![0].snippet).toHaveLength(MAX_SNIPPET_CHARS);
  });

  it("marks a capped snippet with a trailing ellipsis, reserving space so the cap doesn't clip it off", () => {
    // #2306-era finding: the note behind this snippet can be 1000s of chars long, and a
    // bare slice with no marker is indistinguishable from a note that just happens to be
    // exactly this short — a user has no way to tell "this is everything" from "this is
    // the first 280 characters of a lot more". Mirrors the backend's own fix for the
    // model-facing payload (digigraph/orchestration/builtin.py's _mark_truncated_excerpts);
    // this is the same problem one layer up, for the human reading the activity panel.
    const full = "x".repeat(MAX_SNIPPET_CHARS + 200);
    const out = sanitizeActivitySpan(
      span({
        operation: "retrieve",
        status: "completed",
        documents: [{ title: "T", path: "p", snippet: full }],
      }),
    );
    const snippet = out!.documents![0].snippet!;
    // Exactly MAX_SNIPPET_CHARS total -- the ellipsis is RESERVED space, not appended
    // after the cap, or a naive re-clip anywhere downstream would slice the marker off.
    expect(snippet).toHaveLength(MAX_SNIPPET_CHARS);
    expect(snippet.endsWith("…")).toBe(true);
    expect(snippet.slice(0, -1)).toBe(full.slice(0, MAX_SNIPPET_CHARS - 1));
  });

  it("does not add an ellipsis to a snippet that was never truncated", () => {
    const out = sanitizeActivitySpan(
      span({
        operation: "retrieve",
        status: "completed",
        documents: [{ title: "T", path: "p", snippet: "A short, complete snippet." }],
      }),
    );
    expect(out!.documents![0].snippet).toBe("A short, complete snippet.");
  });

  it("rejects non-finite year and non-string tier/snippet without dropping the doc", () => {
    const out = sanitizeActivitySpan(
      span({
        operation: "retrieve",
        status: "completed",
        documents: [{ title: "T", path: "p", tier: 1, year: "2024", snippet: 9 }],
      }),
    );
    expect(out!.documents).toEqual([{ title: "T", path: "p" }]);
  });

  it("allowlists brief themes/questions and drops undeclared brief keys", () => {
    const out = sanitizeActivitySpan(
      span({
        operation: "chat",
        status: "completed",
        brief: {
          themes: [
            { label: "Auth", summary: "RS256", internal: true },
            ...Array.from({ length: MAX_BRIEF_THEMES + 3 }, (_, i) => ({
              label: `t${i}`,
              summary: `s${i}`,
            })),
          ],
          questions: Array.from({ length: MAX_BRIEF_QUESTIONS + 2 }, (_, i) => `q${i}`),
          model: "gpt",
        },
      }),
    );
    expect(out!.brief!.themes).toHaveLength(MAX_BRIEF_THEMES);
    expect(out!.brief!.questions).toHaveLength(MAX_BRIEF_QUESTIONS);
    expect(Object.keys(out!.brief!).sort()).toEqual(["questions", "themes"]);
    expect(Object.keys(out!.brief!.themes[0]).sort()).toEqual(["label", "summary"]);
  });

  it("strips documents and brief at labels; preserves documentsWithheld honesty", () => {
    const full: ActivitySpan = {
      operation: "retrieve",
      status: "completed",
      label: "Sources",
      documents: [{ title: "A", path: "p", tier: "t", year: 2020, snippet: "x" }],
      brief: { themes: [{ label: "T", summary: "S" }], questions: ["Q"] },
      reasoningDelta: "think",
    };
    const out = applyActivityDetail(full, "labels")!;
    expect(out.documents).toBeUndefined();
    expect(out.brief).toBeUndefined();
    expect(out.reasoningDelta).toBeUndefined();
    expect(out.documentsWithheld).toBe(true);
    expect("briefWithheld" in out).toBe(false);
  });

  it("brief-only span at labels becomes label row without themes", () => {
    const full: ActivitySpan = {
      operation: "chat",
      status: "completed",
      label: "Research brief",
      brief: { themes: [{ label: "T", summary: "S" }] },
    };
    const out = applyActivityDetail(full, "labels")!;
    expect(out).toEqual({
      operation: "chat",
      status: "completed",
      label: "Research brief",
    });
  });
});

describe("toDigiChatActivity — Phase 2 rich hits + brief", () => {
  it("passes tier/year/snippet through tool_result hits", () => {
    const rows = toDigiChatActivity([
      {
        operation: "retrieve",
        status: "completed",
        label: "Sources",
        toolName: "file_search",
        query: "auth",
        documents: [
          {
            title: "Auth",
            path: "p",
            tier: "peer_reviewed",
            year: 2024,
            snippet: "JWT",
          },
        ],
      },
    ]);
    expect(rows).toEqual([
      {
        kind: "tool_result",
        name: "file_search",
        query: "auth",
        hits: [
          {
            title: "Auth",
            path: "p",
            tier: "peer_reviewed",
            year: 2024,
            snippet: "JWT",
          },
        ],
        count: 1,
      },
    ]);
  });

  it("projects brief spans onto kind brief", () => {
    const rows = toDigiChatActivity([
      {
        operation: "chat",
        status: "completed",
        label: "Research brief",
        brief: {
          themes: [{ label: "Auth", summary: "RS256" }],
          questions: ["Which tenant?"],
        },
      },
    ]);
    expect(rows).toEqual([
      {
        kind: "brief",
        themes: [{ label: "Auth", summary: "RS256" }],
        questions: ["Which tenant?"],
      },
    ]);
  });

  it("projects label-only chat (brief stripped) as trace", () => {
    expect(
      toDigiChatActivity([
        { operation: "chat", status: "completed", label: "Research brief" },
      ]),
    ).toEqual([{ kind: "trace", label: "Research brief", done: true }]);
  });
});

it("messageActivities projects activity parts and ignores digigraphTrace", () => {
  const message = {
    id: "a1",
    role: "assistant",
    parts: [
      {
        type: ACTIVITY_PART_TYPE,
        data: {
          operation: "retrieve",
          status: "completed",
          label: "Sources",
          toolName: "rag_sources",
          documents: [{ title: "Auth", path: "doc-1", tier: "t", year: 2024 }],
        },
      },
      {
        type: "data-digigraphTrace",
        data: { type: "rag_sources", payload: { sources: [{ source_id: "should-not-render" }] } },
      },
    ],
  } as unknown as UIMessage;
  const rows = messageActivities(message);
  expect(rows.some((r) => r.kind === "tool_result")).toBe(true);
  expect(JSON.stringify(rows)).not.toContain("should-not-render");
});
