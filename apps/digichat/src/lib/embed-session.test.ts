// @vitest-environment happy-dom
import { describe, expect, it, beforeEach } from "vitest";
import type { UIMessage } from "ai";
import {
  EMBED_SESSION_MAX_AGE_MS,
  EMBED_SESSION_MAX_MESSAGES,
  clearEmbedSession,
  readEmbedSession,
  writeEmbedSession,
} from "./embed-session";

function message(id: string): UIMessage {
  return { id, role: "user", parts: [{ type: "text", text: id }] };
}

describe("embed session", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("round-trips the transcript and conversation id", () => {
    writeEmbedSession("digithings.ai", "conv-1", [message("a")], 1_000);
    expect(readEmbedSession("digithings.ai", 1_000)).toMatchObject({
      conversationId: "conv-1",
      messages: [message("a")],
    });
  });

  it("drops a stale record", () => {
    writeEmbedSession("digithings.ai", "conv-1", [message("a")], 1_000);
    expect(readEmbedSession("digithings.ai", 1_000 + EMBED_SESSION_MAX_AGE_MS + 1)).toBeNull();
  });

  it("keeps only the newest messages", () => {
    const messages = Array.from({ length: EMBED_SESSION_MAX_MESSAGES + 5 }, (_, i) =>
      message(`m${i}`),
    );
    writeEmbedSession("digithings.ai", null, messages, 1_000);
    const saved = readEmbedSession("digithings.ai", 1_000);
    expect(saved?.messages).toHaveLength(EMBED_SESSION_MAX_MESSAGES);
    expect(saved?.messages[0]?.id).toBe("m5");
  });

  it("clears on demand and refuses a malformed payload", () => {
    writeEmbedSession("digithings.ai", "conv-1", [message("a")], 1_000);
    clearEmbedSession("digithings.ai");
    expect(readEmbedSession("digithings.ai", 1_000)).toBeNull();
    localStorage.setItem("digichat_embed_session:digithings.ai", "{\"v\":1}");
    expect(readEmbedSession("digithings.ai", 1_000)).toBeNull();
  });
});
