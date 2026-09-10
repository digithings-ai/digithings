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
      title: "file search",
    });
    expect(chunks.some((c) => c.type === "tool-input-available")).toBe(true);
    expect(chunks.some((c) => c.type === "tool-output-available")).toBe(true);
    const start = chunks.find((c) => c.type === "tool-input-start");
    const out = chunks.find((c) => c.type === "tool-output-available");
    expect(out?.toolCallId).toBe(start?.toolCallId);
    const delta = chunks.find((c) => c.type === "tool-input-delta");
    expect(delta?.inputTextDelta).toBe(JSON.stringify({ query: "auth" }, null, 2));
    const input = chunks.find((c) => c.type === "tool-input-available");
    expect(input?.input).toEqual({ query: "auth" });
    expect(out?.output).toMatchObject({ query: "auth" });
    expect(out?.output).toHaveProperty("durationMs");
  });

  it("mints a new toolCallId per invocation of the same tool name", () => {
    const chunks = collect([
      {
        operation: "execute_tool",
        status: "started",
        label: "digisearch",
        toolName: "digisearch",
        query: "first",
      },
      {
        operation: "retrieve",
        status: "completed",
        label: "Sources",
        toolName: "digisearch",
        query: "first",
        documents: [{ title: "A", path: "a.md", snippet: "alpha" }],
      },
      {
        operation: "execute_tool",
        status: "started",
        label: "digisearch",
        toolName: "digisearch",
        query: "second",
      },
      {
        operation: "retrieve",
        status: "completed",
        label: "Sources",
        toolName: "digisearch",
        query: "second",
        documents: [{ title: "B", path: "b.md", snippet: "beta" }],
      },
    ]);
    const starts = chunks.filter((c) => c.type === "tool-input-start");
    expect(starts).toHaveLength(2);
    expect(starts[0]?.toolCallId).not.toBe(starts[1]?.toolCallId);
    const outputs = chunks.filter((c) => c.type === "tool-output-available");
    expect(outputs).toHaveLength(2);
    expect(outputs[0]?.toolCallId).toBe(starts[0]?.toolCallId);
    expect(outputs[1]?.toolCallId).toBe(starts[1]?.toolCallId);
    expect(outputs[0]?.output).toMatchObject({
      query: "first",
      hitCount: 1,
      documents: [{ title: "A", path: "a.md", snippet: "alpha" }],
    });
    expect(outputs[0]?.output).not.toHaveProperty("status");
    expect(outputs[0]?.output).not.toHaveProperty("label");
  });

  it("does not emit tool-input-available on a started call until finish (avoids Approve)", () => {
    const chunks = collect(
      {
        operation: "execute_tool",
        status: "started",
        label: "digivault_search_notes",
        toolName: "digivault_search_notes",
        query: "digigraph",
      },
      false,
    );
    expect(chunks.some((c) => c.type === "tool-input-start")).toBe(true);
    expect(chunks.some((c) => c.type === "tool-input-available")).toBe(false);
    expect(chunks.some((c) => c.type === "tool-output-available")).toBe(false);
  });

  it("auto-completes leftover read tools on finish so Allow/Deny never sticks", () => {
    const chunks = collect({
      operation: "execute_tool",
      status: "started",
      label: "digivault_get_note",
      toolName: "digivault_get_note",
      toolInput: { vault_paths: ["clients/digithings/architecture.md"] },
    });
    expect(chunks.some((c) => c.type === "tool-input-available")).toBe(true);
    const out = chunks.find((c) => c.type === "tool-output-available");
    expect(out?.output).toMatchObject({
      vault_paths: ["clients/digithings/architecture.md"],
    });
    const start = chunks.find((c) => c.type === "tool-input-start");
    expect(out?.toolCallId).toBe(start?.toolCallId);
  });

  it("keeps started MCP args on the retrieve result row", () => {
    const chunks = collect([
      {
        operation: "execute_tool",
        status: "started",
        label: "digivault_get_note",
        toolName: "digivault_get_note",
        toolInput: { vault_paths: ["clients/digithings/architecture.md"] },
      },
      {
        operation: "retrieve",
        status: "completed",
        label: "Loaded full note",
        toolName: "digivault_get_note",
        documents: [
          {
            title: "architecture",
            path: "clients/digithings/architecture.md",
            body: "# digigraph\norchestration hub",
          },
        ],
      },
    ]);
    const out = chunks.find((c) => c.type === "tool-output-available");
    expect(out?.output).toMatchObject({
      vault_paths: ["clients/digithings/architecture.md"],
      hitCount: 1,
      documents: [
        expect.objectContaining({
          path: "clients/digithings/architecture.md",
          body: "# digigraph\norchestration hub",
        }),
      ],
    });
    expect(chunks.filter((c) => c.type === "tool-output-available")).toHaveLength(1);
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
    expect(out?.output).toMatchObject({ documentsWithheld: true, query: "auth", hitCount: 0 });
    expect(out?.output).not.toHaveProperty("documents");
  });

  it("keeps hitCount when labels withheld documents", () => {
    const chunks = collect({
      operation: "retrieve",
      status: "completed",
      label: "Sources",
      toolName: "digisearch",
      query: "digigraph",
      documentsWithheld: true,
      hitCount: 7,
    });
    const out = chunks.find((c) => c.type === "tool-output-available");
    expect(out?.output).toMatchObject({
      query: "digigraph",
      hitCount: 7,
      documentsWithheld: true,
    });
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

  it("folds page-context.html into the user text for digigraph", () => {
    const html = "<main><h1>Brief</h1></main>";
    const messages = [
      {
        id: "u1",
        role: "user",
        parts: [
          { type: "text", text: "What changed?" },
          {
            type: "file",
            filename: "page-context.html",
            mediaType: "text/html",
            url: `data:text/html;charset=utf-8,${encodeURIComponent(html)}`,
          },
        ],
      },
    ] as unknown as UIMessage[];
    const out = uiMessagesForUpstream(messages);
    expect(out[0]?.parts).toHaveLength(1);
    expect(out[0]?.parts[0]).toMatchObject({ type: "text" });
    const text = out[0]?.parts[0]?.type === "text" ? out[0].parts[0].text : "";
    expect(text).toContain("What changed?");
    expect(text).toContain("Page HTML snapshot");
    expect(text).toContain("<h1>Brief</h1>");
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
