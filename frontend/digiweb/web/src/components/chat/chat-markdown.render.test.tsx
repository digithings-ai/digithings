/**
 * SSR smoke tests for <ChatMarkdown source>: the server markup a reader gets
 * with JS disabled. Math is the interesting case — remark-math + rehype-katex
 * run inside the unified pipeline, so laid-out KaTeX is in the HTML before a
 * byte of client JS arrives. Mermaid is the opposite: it needs a live DOM, so
 * the server pass must ship the diagram source verbatim (see
 * chat-mermaid.client.test.tsx for what happens once the effect runs).
 */
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { ChatMarkdown } from "./ChatMarkdown";

describe("ChatMarkdown — frame", () => {
  it("keeps the children-only path as a bare .chat-md frame", () => {
    const html = renderToStaticMarkup(
      <ChatMarkdown className="extra">
        <p>hand-built</p>
      </ChatMarkdown>,
    );
    expect(html).toContain("chat-md");
    expect(html).toContain("extra");
    expect(html).toContain("<p>hand-built</p>");
    expect(html).not.toContain("katex");
  });

  it("renders source first, then children (the streaming-cursor slot)", () => {
    const html = renderToStaticMarkup(
      <ChatMarkdown source="text">
        <span className="cursor-slot" />
      </ChatMarkdown>,
    );
    expect(html.indexOf("text")).toBeLessThan(html.indexOf("cursor-slot"));
  });
});

describe("ChatMarkdown — markdown grammar", () => {
  it("emits bare tags for the chat-core combinators", () => {
    const html = renderToStaticMarkup(
      <ChatMarkdown source={"# Head\n\nA **bold** word.\n\n- one\n- two\n"} />,
    );
    expect(html).toContain("<h1>Head</h1>");
    expect(html).toContain("<strong>bold</strong>");
    expect(html).toContain("<li>one</li>");
  });

  it("boxes a GFM table so a wide one scrolls instead of stretching the turn", () => {
    const html = renderToStaticMarkup(
      <ChatMarkdown source={"| a | b |\n| - | - |\n| 1 | 2 |\n"} />,
    );
    expect(html).toContain("chat-md-table");
    expect(html).toContain("<th>a</th>");
  });

  it("gives a fenced block the copy caption and inline code a bare tag", () => {
    const html = renderToStaticMarkup(
      <ChatMarkdown source={"```python\nx = 1\n```\n\nand `inline` too\n"} />,
    );
    expect(html).toContain("chat-md-code");
    expect(html).toContain("python");
    expect(html).toContain("x = 1");
    expect(html).toContain("<code>inline</code>");
  });

  it("renders only http(s) links", () => {
    const html = renderToStaticMarkup(
      <ChatMarkdown source={"[ok](https://example.com) [no](javascript:alert(1))"} />,
    );
    expect(html).toContain('href="https://example.com"');
    expect(html).toContain('rel="noopener noreferrer"');
    expect(html).not.toContain("javascript:");
  });
});

describe("ChatMarkdown — math", () => {
  it("renders inline $…$ as KaTeX in the server markup", () => {
    const html = renderToStaticMarkup(<ChatMarkdown source={"mass–energy: $E = mc^2$"} />);
    expect(html).toContain("katex");
    // inline math is not a display block
    expect(html).not.toContain("katex-display");
    // KaTeX ships MathML for AT alongside the visual HTML
    expect(html).toContain("<math");
    expect(html).toContain("katex-html");
  });

  it("renders fenced $$ … $$ (delimiters on their own lines) as display KaTeX", () => {
    const html = renderToStaticMarkup(
      <ChatMarkdown source={"before\n\n$$\n\\sum_{i=1}^{n} i\n$$\n\nafter"} />,
    );
    expect(html).toContain("katex-display");
    expect(html).toContain("before");
    expect(html).toContain("after");
  });

  it("renders block $$…$$ as display KaTeX", () => {
    const html = renderToStaticMarkup(
      <ChatMarkdown source={"before\n\n$$\\int_0^1 x^2\\,dx = \\frac{1}{3}$$\n\nafter"} />,
    );
    expect(html).toContain("katex-display");
    expect(html).toContain("mfrac");
    expect(html).toContain("before");
    expect(html).toContain("after");
  });

  it("keeps unparseable TeX readable instead of throwing", () => {
    const html = renderToStaticMarkup(<ChatMarkdown source={"$\\frac{1}{$"} />);
    expect(html).toContain("chat-md");
    // katex renders the offending source rather than blowing up the turn
    expect(html.length).toBeGreaterThan(0);
  });

  it("leaves prose without delimiters alone", () => {
    const html = renderToStaticMarkup(<ChatMarkdown source={"no math here at all"} />);
    expect(html).not.toContain("katex");
  });
});

describe("ChatMarkdown — mermaid", () => {
  const diagram = "graph TD;\n  A-->B;\n";

  it("renders a mermaid fence as the diagram container", () => {
    const html = renderToStaticMarkup(<ChatMarkdown source={"```mermaid\n" + diagram + "```\n"} />);
    expect(html).toContain("chat-md-mermaid");
    expect(html).toContain("mermaid</span>");
    // not the plain fenced-code figure
    expect(html).not.toContain("chat-md-code");
  });

  it("degrades to the verbatim source before any client JS runs", () => {
    const html = renderToStaticMarkup(<ChatMarkdown source={"```mermaid\n" + diagram + "```\n"} />);
    expect(html).toContain('data-state="pending"');
    expect(html).toContain("A--&gt;B;");
    expect(html).not.toContain("<svg");
  });

  it("does not swallow the rest of the turn", () => {
    const html = renderToStaticMarkup(
      <ChatMarkdown source={"intro\n\n```mermaid\n" + diagram + "```\n\noutro\n"} />,
    );
    expect(html).toContain("intro");
    expect(html).toContain("outro");
  });
});
