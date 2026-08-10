import { describe, it, expect } from "vitest";
import {
  DEFAULT_CHAT_EMBED_HOST,
  EMBED_READY_TIMEOUT_MS,
  OCC_CHAT_EMBED_HOST,
  THEME,
  buildEmbedThemeMessage,
  readParentDocumentTheme,
} from "@/components/ChatEmbedShell";

describe("ChatEmbedShell contracts", () => {
  it("keeps OCC as a virtual host distinct from the digithings parent", () => {
    expect(DEFAULT_CHAT_EMBED_HOST).toBe("digithings.ai");
    expect(OCC_CHAT_EMBED_HOST).toBe("occ.digithings.ai");
    expect(OCC_CHAT_EMBED_HOST).not.toBe(DEFAULT_CHAT_EMBED_HOST);
  });

  it("allows cold-start before treating a missing ready as a load failure", () => {
    expect(EMBED_READY_TIMEOUT_MS).toBeGreaterThanOrEqual(30_000);
  });

  it("posts digichat:theme with light|dark only", () => {
    expect(THEME).toBe("digichat:theme");
    expect(buildEmbedThemeMessage("light")).toEqual({
      type: "digichat:theme",
      theme: "light",
      ts: expect.any(Number),
    });
    expect(buildEmbedThemeMessage("dark", 42)).toEqual({
      type: "digichat:theme",
      theme: "dark",
      ts: 42,
    });
  });

  it("reads parent html data-theme as light or dark", () => {
    expect(readParentDocumentTheme({ getAttribute: () => "light" })).toBe("light");
    expect(readParentDocumentTheme({ getAttribute: () => "dark" })).toBe("dark");
    expect(readParentDocumentTheme({ getAttribute: () => null })).toBe("dark");
  });
});
