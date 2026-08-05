import { describe, it, expect, afterEach, vi } from "vitest";
import { buildDigichatEmbedSrc, getDigichatEmbedOrigin } from "./digichatEmbed";

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("digichatEmbed", () => {
  it("builds /embed URL with host and without token", () => {
    vi.stubEnv("NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN", "https://digithings.ai");
    const src = buildDigichatEmbedSrc({ parentOrigin: "https://digithings.ai" });
    expect(src).toBe("https://digithings.ai/embed?host=https%3A%2F%2Fdigithings.ai");
    expect(src).not.toMatch(/token=/);
  });

  it("defaults to digithings.ai when env unset", () => {
    expect(getDigichatEmbedOrigin()).toBe("https://digithings.ai");
  });

  it("reads origin from env", () => {
    vi.stubEnv("NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN", "https://digithings.ai");
    expect(getDigichatEmbedOrigin()).toBe("https://digithings.ai");
  });
});
