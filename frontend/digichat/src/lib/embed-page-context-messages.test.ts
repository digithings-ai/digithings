import { describe, expect, it } from "vitest";
import {
  PAGE_CONTEXT_MESSAGE_TYPE,
  buildPageContextMessage,
  extractVisiblePageText,
  formatPageContextForPrompt,
  parsePageContextMessage,
  sanitizePageHtml,
} from "@/lib/embed-page-context-messages";

describe("embed-page-context-messages", () => {
  it("builds and parses a valid page-context message from the parent origin", () => {
    const msg = buildPageContextMessage("Hello   world", {
      html: "<main><p>Hello</p></main>",
      screenshotDataUrl: "data:image/png;base64,abc",
      ts: Date.now(),
    });
    expect(msg.type).toBe(PAGE_CONTEXT_MESSAGE_TYPE);
    expect(msg.text).toBe("Hello world");
    expect(msg.html).toContain("<main>");

    const parsed = parsePageContextMessage(
      {
        origin: "https://app.example",
        data: msg,
      } as MessageEvent,
      "https://app.example",
    );
    expect(parsed?.text).toBe("Hello world");
    expect(parsed?.html).toContain("<p>Hello</p>");
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

    expect(
      parsePageContextMessage(
        {
          origin: "https://app.example",
          data: {
            ...msg,
            screenshotDataUrl: "data:image/svg+xml,<svg></svg>",
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

  it('sanitizes HTML before accept and drops hidden/password values', () => {
    const clean = sanitizePageHtml(
      '<div onclick="x()"><script>bad()</script>' +
        '<input type="hidden" value="csrf">' +
        '<input type="text" value="seen">' +
        '<p>ok</p></div>',
    );
    expect(clean).toContain("<p>ok</p>");
    expect(clean).not.toContain("script");
    expect(clean).not.toContain("onclick");
    expect(clean).not.toContain("csrf");
    expect(clean).not.toContain('value="seen"');
  });

  it("formats prompt with HTML preferred over text-only, without inlining screenshot bytes", () => {
    const formatted = formatPageContextForPrompt({
      text: "Visible FAQ",
      html: "<section><h1>FAQ</h1></section>",
      screenshotDataUrl: "data:image/png;base64," + "x".repeat(100),
    });
    expect(formatted).toContain("Page HTML snapshot");
    expect(formatted).toContain("<h1>FAQ</h1>");
    expect(formatted).toContain("Visible FAQ");
    expect(formatted).toContain("screenshot");
    expect(formatted).toContain("vision multimodal is not enabled");
    expect(formatted).not.toContain("base64");
  });
});
