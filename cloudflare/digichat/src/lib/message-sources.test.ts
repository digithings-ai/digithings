// @vitest-environment happy-dom
import { describe, expect, it } from "vitest";
import type { UIMessage } from "ai";
import { messageSourceCitations } from "./message-sources";

describe("messageSourceCitations", () => {
  it("reads source-url and source-document parts", () => {
    const message = {
      id: "a1",
      role: "assistant",
      parts: [
        { type: "text", text: "answer" },
        { type: "source-url", sourceId: "s1", url: "https://ex.ample/a", title: "A" },
        {
          type: "source-document",
          sourceId: "s2",
          mediaType: "text/plain",
          title: "Note",
          filename: "vault/note.md",
        },
      ],
    } as UIMessage;
    expect(messageSourceCitations(message)).toEqual([
      { title: "A", path: "https://ex.ample/a" },
      { title: "Note", path: "vault/note.md" },
    ]);
  });

  it("falls back to branded activity hydrate when no source-* parts", () => {
    const message = {
      id: "a2",
      role: "assistant",
      parts: [
        {
          type: "data-digichatActivity",
          id: "x",
          data: {
            operation: "retrieve",
            status: "completed",
            label: "search",
            toolName: "digisearch",
            query: "jwt",
            documents: [{ title: "Old", path: "docs/old.md" }],
          },
        },
      ],
    } as UIMessage;
    expect(messageSourceCitations(message)).toEqual([{ title: "Old", path: "docs/old.md" }]);
  });
});
