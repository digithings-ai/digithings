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
    expect(html).toContain("<strong>bold</strong>");
    expect(html).toContain("<li>one</li>");
  });

  it("downshifts headings two levels so model output cannot claim the page h1", () => {
    // Neither digichat /embed nor digithings.ai/chat has an <h1> on its transcript
    // route, so an un-downshifted `#` from streamed text would become the
    // document's top-level heading — a real outline and screen-reader defect. The
    // renderer this replaced (digichat-ui's MiniMarkdown) mapped h1→h3 … h4→h6;
    // this pins that behaviour so it cannot be dropped again silently.
    const html = renderToStaticMarkup(
      <ChatMarkdown source={"# One\n\n## Two\n\n### Three\n\n#### Four\n"} />,
    );
    expect(html).toContain("<h3>One</h3>");
    expect(html).toContain("<h4>Two</h4>");
    expect(html).toContain("<h5>Three</h5>");
    expect(html).toContain("<h6>Four</h6>");
    expect(html).not.toContain("<h1>");
    expect(html).not.toContain("<h2>");
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
  // Single-dollar inline math is deliberately OFF (`singleDollarTextMath: false`).
  // It cannot coexist with currency: remark-math treats the second `$` in any
  // paragraph as a closing delimiter, so "$29 ... $99" mangles into math. Currency
  // is far commoner than inline math in a docs answer, so `$…$` stays literal and
  // real notation uses `$$…$$`, which still renders. See ChatMarkdownSource.
  it("leaves single-dollar spans literal rather than parsing them as math", () => {
    const html = renderToStaticMarkup(<ChatMarkdown source={"mass–energy: $E = mc^2$"} />);
    expect(html).not.toContain("katex");
    expect(html).toContain("$E = mc^2$");
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

// Regression: remark-math defaults `singleDollarTextMath: true`, so any paragraph
// with two `$` parsed as inline math — "$29 ... $99" re-set the prose between them
// as italic math with the spaces collapsed and ate the second `$`. Currency is far
// commoner than inline math in a docs answer, and this renders for a quant stack.
describe("currency in prose", () => {
  it("leaves two dollar figures in a sentence alone", () => {
    const html = renderToStaticMarkup(
      <ChatMarkdown source="Our starter plan is $29 per month and the team plan is $99 per month." />
    );
    expect(html).not.toContain("katex");
    expect(html).toContain("$29");
    expect(html).toContain("$99");
  });

  it("leaves shell variables alone", () => {
    const html = renderToStaticMarkup(
      <ChatMarkdown source="Use the $HOME var and the $PATH var in your shell." />
    );
    expect(html).not.toContain("katex");
    expect(html).toContain("$HOME");
    expect(html).toContain("$PATH");
  });

  it("still renders block math", () => {
    const html = renderToStaticMarkup(<ChatMarkdown source={"$$e^{i\\pi}+1=0$$"} />);
    expect(html).toContain("katex");
  });
});
