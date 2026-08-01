import { describe, it, expect } from "vitest";
import {
  sanitizeActivitySpan,
  applyActivityDetail,
  toDigiChatActivity,
  MAX_LABEL_CHARS,
  MAX_DOCUMENTS,
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

  it("passes everything through at full", () => {
    expect(applyActivityDetail(full, "full")).toEqual(full);
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
    expect(
      toDigiChatActivity([
        started("file_search"),
        { ...finished("file_search", "auth"), status: "failed" },
      ])
    ).toEqual([{ kind: "tool_result", name: "file_search", query: "auth", hits: [], count: 0 }]);
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
});
