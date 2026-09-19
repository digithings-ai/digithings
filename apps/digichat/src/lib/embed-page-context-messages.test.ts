/** @vitest-environment happy-dom */
import { describe, expect, it } from "vitest";
import {
  PAGE_CONTEXT_ATTACHMENT_NAME,
  PAGE_CONTEXT_MESSAGE_TYPE,
  buildPageContextMessage,
  decodeDataUrlText,
  expandPageContextFileParts,
  extractVisiblePageText,
  formatPageContextForPrompt,
  pageContextCreateAttachment,
  pageContextFileUiPart,
  parsePageContextMessage,
  sanitizePageHtml,
  shapeUserMessageParts,
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

  it("re-allowlists html on the receiver even if the parent skipped sanitizing", () => {
    const parsed = parsePageContextMessage(
      {
        origin: "https://app.example",
        data: {
          type: PAGE_CONTEXT_MESSAGE_TYPE,
          text: "ok",
          html:
            '<div hidden>HIDDEN-NESTED</div><p>Visible</p>' +
            '<a href="/x?token=tok_live">link</a>',
          ts: Date.now(),
        },
      } as MessageEvent,
      "https://app.example",
    );
    expect(parsed?.html).toContain("Visible");
    expect(parsed?.html).not.toContain("HIDDEN-NESTED");
    expect(parsed?.html).not.toContain("tok_live");
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

  it("shapes a user turn as question text plus a page-context.html document part", () => {
    const ctx = buildPageContextMessage("Visible FAQ", {
      html: "<section><h1>FAQ</h1></section>",
    });
    const parts = shapeUserMessageParts("Why is this sized this way?", ctx);
    expect(parts[0]).toEqual({
      type: "text",
      text: "Why is this sized this way?",
    });
    expect(parts[1]).toMatchObject({
      type: "file",
      filename: PAGE_CONTEXT_ATTACHMENT_NAME,
      mediaType: "text/html",
    });
    const file = parts[1];
    expect(file && file.type === "file").toBe(true);
    if (file && file.type === "file") {
      expect(decodeDataUrlText(file.url)).toContain("<h1>FAQ</h1>");
      expect(file.url).not.toContain("base64");
    }
    expect(parts.map((p) => (p.type === "text" ? p.text : "")).join("")).not.toContain(
      "Page HTML snapshot",
    );

    const attachment = pageContextCreateAttachment(ctx);
    expect(attachment?.name).toBe(PAGE_CONTEXT_ATTACHMENT_NAME);
    expect(attachment?.type).toBe("document");
    expect(attachment?.content[0]?.type).toBe("file");
  });

  it("falls back to a text/plain page-context.html part when HTML is absent", () => {
    const file = pageContextFileUiPart({ text: "House book" });
    expect(file?.filename).toBe(PAGE_CONTEXT_ATTACHMENT_NAME);
    expect(file?.mediaType).toBe("text/plain");
    expect(decodeDataUrlText(file!.url)).toBe("House book");
  });

  it("expands the document part into upstream text once so digigraph sees the snapshot", () => {
    const ctx = buildPageContextMessage("Visible FAQ", {
      html: "<section><h1>FAQ</h1></section>",
    });
    const shaped = shapeUserMessageParts("What changed?", ctx);
    const expanded = expandPageContextFileParts([
      { role: "user", parts: shaped },
    ]);
    expect(expanded[0]?.parts).toHaveLength(1);
    expect(expanded[0]?.parts[0]).toMatchObject({ type: "text" });
    const text = expanded[0]?.parts[0]?.type === "text" ? expanded[0].parts[0].text : "";
    expect(text).toContain("Page HTML snapshot");
    expect(text).toContain("<h1>FAQ</h1>");
    expect(text).toContain("Visible FAQ");
    expect(text).toContain("What changed?");
    expect(expandPageContextFileParts(expanded)[0]?.parts[0]).toEqual(expanded[0]?.parts[0]);
  });

  it("preserves screenshot acknowledgement when expanding from the document part", () => {
    const ctx = buildPageContextMessage("Visible FAQ", {
      html: "<section><h1>FAQ</h1></section>",
      screenshotDataUrl: "data:image/png;base64,abc",
    });
    const expanded = expandPageContextFileParts([
      { role: "user", parts: shapeUserMessageParts("What changed?", ctx) },
    ]);
    const text = expanded[0]?.parts[0]?.type === "text" ? expanded[0].parts[0].text : "";
    expect(text).toContain("screenshot");
    expect(text).toContain("vision multimodal is not enabled");
    expect(text).not.toContain("base64");
    expect(text).not.toContain("digichat:page-context-screenshot");
  });
});
