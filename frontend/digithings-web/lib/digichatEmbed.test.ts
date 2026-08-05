import { describe, it, expect, afterEach, vi } from "vitest";
import { buildDigichatEmbedSrc, getDigichatEmbedOrigin } from "./digichatEmbed";

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("digichatEmbed", () => {
  it("builds /embed URL with host and without token", () => {
    vi.stubEnv("NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN", "https://chat.digithings.ai");
    const src = buildDigichatEmbedSrc({ parentOrigin: "https://digithings.ai" });
    expect(src).toBe("https://chat.digithings.ai/embed?host=https%3A%2F%2Fdigithings.ai");
    expect(src).not.toMatch(/token=/);
  });

  it("reads origin from env", () => {
    vi.stubEnv("NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN", "https://chat.digithings.ai");
    expect(getDigichatEmbedOrigin()).toBe("https://chat.digithings.ai");
  });
});
