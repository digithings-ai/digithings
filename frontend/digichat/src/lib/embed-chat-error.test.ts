import { describe, expect, it } from "vitest";
import { formatEmbedChatError } from "./embed-chat-error";

describe("formatEmbedChatError", () => {
  it("returns null for empty errors", () => {
    expect(formatEmbedChatError(undefined)).toBeNull();
  });

  it("parses embed_disabled JSON bodies", () => {
    const msg = formatEmbedChatError(
      new Error(
        JSON.stringify({
          error: "embed_disabled",
          message: "Embed requires DIGICHAT_EMBED_ENABLED=1.",
        }),
      ),
    );
    expect(msg).toBe("Embed requires DIGICHAT_EMBED_ENABLED=1.");
  });

  it("detects embed_disabled in plain text", () => {
    expect(formatEmbedChatError(new Error('{"error":"embed_disabled"}'))).toContain(
      "not enabled",
    );
  });

  it("parses trial_gate JSON bodies instead of leaking the raw 402 payload", () => {
    const msg = formatEmbedChatError(
      new Error(
        JSON.stringify({
          error: "trial_gate",
          message: "Complete the free trial form to keep chatting.",
        }),
      ),
    );
    expect(msg).toBe("Complete the free trial form to keep chatting.");
  });
});
