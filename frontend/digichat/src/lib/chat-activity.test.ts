import { describe, it, expect } from "vitest";
import {
  sanitizeActivitySpan,
  applyActivityDetail,
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
