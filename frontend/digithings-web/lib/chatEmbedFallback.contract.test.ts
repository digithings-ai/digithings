import { describe, expect, it } from "vitest";
import { resolveDigichatEmbedOrigin } from "./security-headers.mjs";

/**
 * Contract for #2068: unset/invalid embed origin → Pages DigiChatSession
 * fallback; valid origin → iframe ChatEmbedShell. The page wires this via
 * `resolveDigichatEmbedOrigin()` (same helper as CSP).
 */
describe("digithings.ai/chat embed vs Pages fallback", () => {
  it("treats missing embed origin as Pages DigiChatSession fallback", () => {
    expect(resolveDigichatEmbedOrigin({})).toBeNull();
    expect(
      resolveDigichatEmbedOrigin({
        NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN: "   ",
      }),
    ).toBeNull();
  });

  it("treats a valid origin as iframe ChatEmbedShell path", () => {
    expect(
      resolveDigichatEmbedOrigin({
        NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN: "https://digichat.digithings.ai",
      }),
    ).toBe("https://digichat.digithings.ai");
  });
});
