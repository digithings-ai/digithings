import { describe, expect, it } from "vitest";
import type { UIMessage } from "ai";
import type { ActivitySpan } from "@/lib/chat-activity";
import {
  CONVERSATION_PART_TYPE,
  conversationIdFromParts,
  createActivityWriteContext,
  finishStandardActivity,
  uiMessagesForUpstream,
  writeStandardActivity,
} from "./ui-stream-parts";

function collect(span: ActivitySpan | ActivitySpan[], finish = true): Record<string, unknown>[] {
  const chunks: Record<string, unknown>[] = [];
  const writer = {
    write: (c: Record<string, unknown>) => chunks.push(c),
  };
  const ctx = createActivityWriteContext();
  for (const s of Array.isArray(span) ? span : [span]) {
    writeStandardActivity(writer as Parameters<typeof writeStandardActivity>[0], s, ctx);
  }
  if (finish) finishStandardActivity(writer as Parameters<typeof finishStandardActivity>[0], ctx);
  return chunks;
}

describe("writeStandardActivity", () => {
  it("never emits branded activity part types", () => {
    const chunks = collect({
      operation: "execute_tool",
      status: "started",
      label: "Searching…",
      toolName: "file_search",
      query: "auth",
    });
    const types = chunks.map((c) => c.type);
    expect(types).not.toContain("data-digichatActivity");
    expect(types).not.toContain("data-digigraphTrace");
    expect(types).toContain("tool-input-start");
  });

  it("maps execute_tool started/completed onto tool input/output chunks", () => {
    const chunks = collect([
      {
        operation: "execute_tool",
        status: "started",
        label: "file_search",
        toolName: "file_search",
        query: "auth",
      },
      {
        operation: "execute_tool",
        status: "completed",
        label: "file_search",
        toolName: "file_search",
        query: "auth",
      },
    ]);
    expect(chunks[0]).toMatchObject({
      type: "tool-input-start",
      toolName: "file_search",
      title: "file_search",
    });
    expect(chunks.some((c) => c.type === "tool-input-available")).toBe(true);
    expect(chunks.some((c) => c.type === "tool-output-available")).toBe(true);
    const start = chunks.find((c) => c.type === "tool-input-start");
    const out = chunks.find((c) => c.type === "tool-output-available");
    expect(out?.toolCallId).toBe(start?.toolCallId);
  });

  it("maps retrieve documents to source-url or source-document plus tool output", () => {
    const chunks = collect({
      operation: "retrieve",
      status: "completed",
      label: "Sources",
      toolName: "rag_sources",
      query: "auth",
      documents: [
        { title: "Auth", path: "https://x/auth", snippet: "JWT" },
        { title: "Note", path: "vault/note.md", body: "# hi" },
      ],
    });
    expect(chunks.some((c) => c.type === "tool-output-available")).toBe(true);
    expect(chunks).toContainEqual(
      expect.objectContaining({
        type: "source-url",
        url: "https://x/auth",
        title: "Auth",
      }),
    );
    expect(chunks).toContainEqual(
      expect.objectContaining({
        type: "source-document",
        title: "Note",
        filename: "vault/note.md",
        mediaType: "text/markdown",
      }),
    );
  });

  it("does not emit source parts when documents were withheld", () => {
    const chunks = collect({
      operation: "retrieve",
      status: "completed",
      label: "Sources",
      toolName: "file_search",
      query: "auth",
      documentsWithheld: true,
    });
    expect(chunks.some((c) => String(c.type).startsWith("source-"))).toBe(false);
    const out = chunks.find((c) => c.type === "tool-output-available");
    expect(out?.output).toMatchObject({ documentsWithheld: true });
  });

  it("maps reasoningDelta onto reasoning chunks and closes on finish", () => {
    const chunks = collect({
      operation: "chat",
      status: "started",
      label: "Thinking",
      reasoningDelta: "step 1",
    });
    expect(chunks.map((c) => c.type)).toEqual([
      "reasoning-start",
      "reasoning-delta",
      "reasoning-end",
    ]);
    expect(chunks[1]).toMatchObject({ delta: "step 1" });
  });

  it("maps opaque chat progress to unbranded data-status", () => {
    const chunks = collect({
      operation: "chat",
      status: "started",
      label: "Searching…",
    });
    expect(chunks[0]).toMatchObject({
      type: "data-status",
      transient: true,
      data: { status: "started", label: "Searching…" },
    });
  });

  it("maps a research brief onto data-status.brief", () => {
    const chunks = collect({
      operation: "chat",
      status: "completed",
      label: "Research brief",
      brief: { themes: [{ label: "Auth", summary: "RS256" }] },
    });
    expect(chunks[0]).toMatchObject({
      type: "data-status",
      data: {
        label: "Research brief",
        brief: { themes: [{ label: "Auth", summary: "RS256" }] },
      },
    });
  });
});

describe("uiMessagesForUpstream", () => {
  it("keeps only text parts so digigraph never sees UI tool/source/data", () => {
    const messages = [
      {
        id: "u1",
        role: "user",
        parts: [{ type: "text", text: "hi" }],
      },
      {
        id: "a1",
        role: "assistant",
        parts: [
          { type: "text", text: "hello" },
          { type: "data-status", data: { label: "Searching…" } },
          { type: "source-url", sourceId: "s1", url: "https://x", title: "X" },
        ],
      },
    ] as unknown as UIMessage[];
    const out = uiMessagesForUpstream(messages);
    expect(out).toHaveLength(2);
    expect(out[1]?.parts).toEqual([{ type: "text", text: "hello" }]);
  });
});

describe("conversationIdFromParts", () => {
  it("reads unbranded data-conversation and the 1.4 alias", () => {
    expect(
      conversationIdFromParts([
        { type: CONVERSATION_PART_TYPE, data: { conversationId: "conv_1" } },
      ]),
    ).toBe("conv_1");
    expect(
      conversationIdFromParts([
        { type: "data-externalConversation", data: { conversationId: "legacy" } },
      ]),
    ).toBe("legacy");
  });
});
