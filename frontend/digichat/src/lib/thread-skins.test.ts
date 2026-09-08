import { describe, expect, it } from "vitest";
import {
  CLONE_SKINS,
  DEFAULT_THREAD_SKIN,
  isCloneSkin,
  isThreadSkin,
  LAYOUT_SKINS,
  parseThreadSkin,
  skinOwnsPageChrome,
  THREAD_SKINS,
  threadSkinChoices,
} from "./thread-skins";

describe("thread skins", () => {
  it("lists the 11 catalog ids plus first-party digichat", () => {
    expect(THREAD_SKINS).toEqual([
      "base",
      "chatgpt",
      "claude",
      "grok",
      "gemini",
      "perplexity",
      "react-ink",
      "expo-react-native",
      "base-assistant-ui",
      "webpage-assistant",
      "product-page-assistant",
      "digichat",
    ]);
    expect(THREAD_SKINS).toHaveLength(12);
    expect(DEFAULT_THREAD_SKIN).toBe("base");
    expect(CLONE_SKINS).toEqual([
      "chatgpt",
      "claude",
      "grok",
      "gemini",
      "perplexity",
    ]);
    expect(threadSkinChoices()).toContain("digichat");
    expect(parseThreadSkin("digichat")).toBe("digichat");
    expect(isCloneSkin("digichat")).toBe(false);
    expect(skinOwnsPageChrome("digichat")).toBe(false);
  });

  it("parses known skins and falls back on unknown", () => {
    expect(parseThreadSkin("ChatGPT")).toBe("chatgpt");
    expect(parseThreadSkin("base-assistant-ui")).toBe("base-assistant-ui");
    expect(parseThreadSkin("not-a-skin")).toBe("base");
    expect(parseThreadSkin("ink")).toBe("base");
    expect(isThreadSkin("claude")).toBe(true);
    expect(isThreadSkin("react-ink")).toBe(true);
    expect(isThreadSkin("not-a-skin")).toBe(false);
    expect(isCloneSkin("chatgpt")).toBe(true);
    expect(isCloneSkin("base")).toBe(false);
  });

  it("marks docs / dashboard / expo templates as page-chrome owners", () => {
    expect(LAYOUT_SKINS).toEqual([
      "webpage-assistant",
      "product-page-assistant",
      "expo-react-native",
    ]);
    expect(skinOwnsPageChrome("webpage-assistant")).toBe(true);
    expect(skinOwnsPageChrome("chatgpt")).toBe(false);
    expect(skinOwnsPageChrome("base")).toBe(false);
  });
});
