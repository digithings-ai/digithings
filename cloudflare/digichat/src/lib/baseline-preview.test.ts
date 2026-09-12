import { afterEach, describe, expect, it, vi } from "vitest";
import { isLocalBaselinePreview, baselineUpstreamChatUrl } from "./baseline-preview";

describe("isLocalBaselinePreview", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("allows loopback in development", () => {
    vi.stubEnv("NODE_ENV", "development");
    expect(isLocalBaselinePreview(new Request("http://127.0.0.1:3005/api/baseline-chat"))).toBe(
      true,
    );
    expect(isLocalBaselinePreview(new Request("http://localhost:3005/api/baseline-chat"))).toBe(
      true,
    );
  });

  it("refuses production even on loopback", () => {
    vi.stubEnv("NODE_ENV", "production");
    expect(isLocalBaselinePreview(new Request("http://127.0.0.1:3005/api/baseline-chat"))).toBe(
      false,
    );
  });

  it("refuses non-loopback hosts in development", () => {
    vi.stubEnv("NODE_ENV", "development");
    expect(
      isLocalBaselinePreview(new Request("https://digithings.ai/api/baseline-chat")),
    ).toBe(false);
  });
});

describe("baselineUpstreamChatUrl", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("defaults to production digithings.ai chat", () => {
    vi.stubEnv("DIGICHAT_BASELINE_UPSTREAM", "");
    expect(baselineUpstreamChatUrl()).toBe("https://digithings.ai/api/chat");
  });

  it("accepts the production URL when set explicitly", () => {
    vi.stubEnv("DIGICHAT_BASELINE_UPSTREAM", "https://digithings.ai/api/chat");
    expect(baselineUpstreamChatUrl()).toBe("https://digithings.ai/api/chat");
  });

  it("rejects other hosts", () => {
    vi.stubEnv("DIGICHAT_BASELINE_UPSTREAM", "https://graph.digithings.ai/v1/chat/completions");
    expect(baselineUpstreamChatUrl()).toBe("https://digithings.ai/api/chat");
  });
});
