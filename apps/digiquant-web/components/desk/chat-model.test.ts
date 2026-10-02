import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { messageRows, replyText, sessionId, sessionRows } from "./chat-model";

describe("official chat reads", () => {
  it("turns missing fields into an em dash and does not invent a reply", () => {
    expect(sessionRows({ sessions: [] })).toEqual([]);
    expect(sessionRows({ sessions: [{ id: "s1", title: null }] })).toEqual([
      { status: "regular", id: "s1", title: "—" },
    ]);
    expect(sessionId({})).toBeNull();
    expect(messageRows({ messages: [{ role: "user", text: null }] })).toEqual([
      { id: "row-0", role: "user", content: "—" },
    ]);
    expect(messageRows({ messages: [] })).toEqual([]);
    expect(replyText({ reply: null })).toBeNull();
    expect(replyText({})).toBeNull();
  });

  it("mounts the digichat thread instead of the scripted stand-in", () => {
    const src = readFileSync(new URL("./desk-chat.tsx", import.meta.url), "utf8");
    expect(src).toContain("DigichatThread");
    expect(src).toContain("DigichatThreadList");
    expect(src).not.toContain("scripted-session");
    expect(src).not.toContain("COMPOSER_HIDDEN");
    expect(src).not.toContain("_strategy-script");
  });
});
