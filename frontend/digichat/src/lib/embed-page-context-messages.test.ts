import { describe, expect, it } from "vitest";
import {
  PAGE_CONTEXT_MESSAGE_TYPE,
  buildPageContextMessage,
  extractVisiblePageText,
  formatPageContextForPrompt,
  parsePageContextMessage,
} from "@/lib/embed-page-context-messages";

describe("embed-page-context-messages", () => {
  it("builds and parses a valid page-context message from the parent origin", () => {
    const msg = buildPageContextMessage("Hello   world", {
      screenshotDataUrl: "data:image/png;base64,abc",
      ts: Date.now(),
    });
    expect(msg.type).toBe(PAGE_CONTEXT_MESSAGE_TYPE);
    expect(msg.text).toBe("Hello world");

    const parsed = parsePageContextMessage(
      {
        origin: "https://app.example",
        data: msg,
      } as MessageEvent,
      "https://app.example",
    );
    expect(parsed?.text).toBe("Hello world");
    expect(parsed?.screenshotDataUrl).toBe("data:image/png;base64,abc");
  });

  it("rejects wrong parent origin and oversized / non-image screenshots", () => {
    const msg = buildPageContextMessage("ok", { ts: Date.now() });
    expect(
      parsePageContextMessage(
        { origin: "https://evil.example", data: msg } as MessageEvent,
        "https://app.example",
      ),
    ).toBeNull();

    expect(
      parsePageContextMessage(
        {
          origin: "https://app.example",
          data: {
            ...msg,
            screenshotDataUrl: "https://evil.example/x.png",
          },
        } as MessageEvent,
        "https://app.example",
      ),
    ).toBeNull();
  });

  it("extracts visible body text only", () => {
    expect(
      extractVisiblePageText({ body: { innerText: "  a\n\nb  " } }, 10),
    ).toBe("a b");
  });

  it("formats prompt without inlining screenshot bytes", () => {
    const formatted = formatPageContextForPrompt({
      text: "Visible FAQ",
      screenshotDataUrl: "data:image/png;base64," + "x".repeat(100),
    });
    expect(formatted).toContain("Visible FAQ");
    expect(formatted).toContain("screenshot");
    expect(formatted).not.toContain("base64");
  });
});
