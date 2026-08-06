import { describe, it, expect } from "vitest";
import { isFirstPartyEmbedHost, FIRST_PARTY_EMBED_HOSTS } from "./embed-first-party";

describe("isFirstPartyEmbedHost", () => {
  it("allows digithings.ai and www only", () => {
    expect(FIRST_PARTY_EMBED_HOSTS.has("digithings.ai")).toBe(true);
    expect(FIRST_PARTY_EMBED_HOSTS.has("www.digithings.ai")).toBe(true);
    expect(isFirstPartyEmbedHost("https://digithings.ai")).toBe(true);
    expect(isFirstPartyEmbedHost("https://www.digithings.ai/chat")).toBe(true);
    expect(isFirstPartyEmbedHost("digithings.ai")).toBe(true);
  });

  it("rejects customer and preview hosts", () => {
    expect(isFirstPartyEmbedHost("https://datatapstream.com")).toBe(false);
    expect(isFirstPartyEmbedHost("https://digithings-ai.pages.dev")).toBe(false);
    expect(isFirstPartyEmbedHost(null)).toBe(false);
  });
});
