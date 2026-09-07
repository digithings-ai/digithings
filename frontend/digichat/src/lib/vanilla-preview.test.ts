import { afterEach, describe, expect, it, vi } from "vitest";
import { isLocalVanillaPreview, vanillaUpstreamChatUrl } from "./vanilla-preview";

describe("isLocalVanillaPreview", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("allows loopback in development", () => {
    vi.stubEnv("NODE_ENV", "development");
    expect(isLocalVanillaPreview(new Request("http://127.0.0.1:3005/api/vanilla-chat"))).toBe(
      true,
    );
    expect(isLocalVanillaPreview(new Request("http://localhost:3005/api/vanilla-chat"))).toBe(
      true,
    );
  });

  it("refuses production even on loopback", () => {
    vi.stubEnv("NODE_ENV", "production");
    expect(isLocalVanillaPreview(new Request("http://127.0.0.1:3005/api/vanilla-chat"))).toBe(
      false,
    );
  });

  it("refuses non-loopback hosts in development", () => {
    vi.stubEnv("NODE_ENV", "development");
    expect(
      isLocalVanillaPreview(new Request("https://digithings.ai/api/vanilla-chat")),
    ).toBe(false);
  });
});

describe("vanillaUpstreamChatUrl", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("defaults to production digithings.ai chat", () => {
    vi.stubEnv("DIGICHAT_VANILLA_UPSTREAM", "");
    expect(vanillaUpstreamChatUrl()).toBe("https://digithings.ai/api/chat");
  });

  it("accepts the production URL when set explicitly", () => {
    vi.stubEnv("DIGICHAT_VANILLA_UPSTREAM", "https://digithings.ai/api/chat");
    expect(vanillaUpstreamChatUrl()).toBe("https://digithings.ai/api/chat");
  });

  it("rejects other hosts", () => {
    vi.stubEnv("DIGICHAT_VANILLA_UPSTREAM", "https://graph.digithings.ai/v1/chat/completions");
    expect(vanillaUpstreamChatUrl()).toBe("https://digithings.ai/api/chat");
  });
});
