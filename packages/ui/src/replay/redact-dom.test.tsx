/**
 * @vitest-environment happy-dom
 */
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { JsonView } from "../components/chat/stock/json-view";
import { REDACTED } from "./redact";
import { redactBlockText, redactSnapshotDom } from "./redact-dom";

function root(html: string): HTMLElement {
  const doc = document.implementation.createHTMLDocument("chat");
  doc.body.innerHTML = html;
  return doc.body;
}

describe("redactSnapshotDom", () => {
  it("replaces a cookie value without eating the rest of the transcript", () => {
    const body = root(
      [
        '<div class="aui-md"><p>Set the header:</p>',
        "<pre><code>Cookie: session=abc123456</code></pre>",
        "<p>Then reload.</p></div>",
        '<div class="aui-assistant-message-content"><p>Done.</p></div>',
      ].join(""),
    );
    redactSnapshotDom(body);
    expect(body.textContent).not.toContain("abc123456");
    expect(body.querySelector("pre > code")?.textContent).toBe(`Cookie: ${REDACTED}`);
    expect(body.querySelectorAll(".aui-md p")[1]?.textContent).toBe("Then reload.");
    expect(body.querySelector(".aui-assistant-message-content p")?.textContent).toBe("Done.");
  });

  it("redacts tool JSON rendered by JsonView by key, whatever the value looks like", () => {
    const html = renderToStaticMarkup(
      <JsonView
        value={{ api_key: "supersecretvalue", password: "abc12", client_secret: "x", query: "ok" }}
      />,
    );
    // React escapes the quotes in text; the rendered JSON is split into token spans.
    expect(html).toContain("&quot;");
    const body = root(`<div data-slot="tool-fallback-content">${html}<p>after</p></div>`);
    redactSnapshotDom(body);
    const text = body.textContent ?? "";
    expect(text).not.toContain("supersecretvalue");
    expect(text).not.toContain("abc12");
    expect(text).toContain('"query": "ok"');
    expect(text).toContain(`"password": "${REDACTED}"`);
    expect(body.querySelector("p")?.textContent).toBe("after");
  });

  it("finds a secret split across inline elements and keeps clean blocks formatted", () => {
    const body = root(
      [
        "<p>Send <code>Authorization:</code> <code>Bearer abcdefgh12345678</code> now.</p>",
        "<p>Plain <strong>bold</strong> text.</p>",
      ].join(""),
    );
    redactSnapshotDom(body);
    expect(body.textContent).not.toContain("abcdefgh12345678");
    expect(body.querySelectorAll("p")[0]?.textContent).toContain("now.");
    expect(body.querySelector("strong")?.textContent).toBe("bold");
  });

  it("redacts attribute values and leaves inlined data: payloads alone", () => {
    const hex = "ab".repeat(24);
    const uri = `data:image/png;base64,${hex}`;
    const body = root(
      `<a href="https://desk.example/chat?token=livevalue123">link</a><img src="${uri}" alt="x">` +
        `<span title="${hex}">t</span>`,
    );
    redactSnapshotDom(body);
    expect(body.querySelector("a")?.getAttribute("href")).toBe(
      `https://desk.example/chat?token=${REDACTED}`,
    );
    expect(body.querySelector("img")?.getAttribute("src")).toBe(uri);
    expect(body.querySelector("span")?.getAttribute("title")).toBe(REDACTED);
  });

  it("leaves CSS text alone", () => {
    const body = root(
      `<style>.a{background:url("data:font/woff2;base64,${"cd".repeat(24)}")}</style>`,
    );
    const before = body.innerHTML;
    redactSnapshotDom(body);
    expect(body.innerHTML).toBe(before);
  });
});

describe("redactBlockText", () => {
  it("keeps JSON without secrets byte for byte", () => {
    const text = '{\n  "tokens": 12,\n  "max_tokens": 4096\n}';
    expect(redactBlockText(text)).toBe(text);
  });
});
