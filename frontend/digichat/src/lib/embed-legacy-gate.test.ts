import { describe, it, expect, afterEach, vi } from "vitest";
import { isLegacyEmbedEnabled } from "./embed-legacy-gate";

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("isLegacyEmbedEnabled", () => {
  it("is off by default", () => {
    expect(isLegacyEmbedEnabled()).toBe(false);
  });

  it("enables when DIGICHAT_LEGACY_EMBED_ENABLED=1", () => {
    vi.stubEnv("DIGICHAT_LEGACY_EMBED_ENABLED", "1");
    expect(isLegacyEmbedEnabled()).toBe(true);
  });

  it("falls back to deprecated DIGICHAT_EMBED_ENABLED=1", () => {
    vi.stubEnv("DIGICHAT_EMBED_ENABLED", "1");
    expect(isLegacyEmbedEnabled()).toBe(true);
  });

  it("prefers DIGICHAT_LEGACY_EMBED_ENABLED when both are set", () => {
    vi.stubEnv("DIGICHAT_LEGACY_EMBED_ENABLED", "1");
    vi.stubEnv("DIGICHAT_EMBED_ENABLED", "0");
    expect(isLegacyEmbedEnabled()).toBe(true);
  });
});
