/**
 * #1418 gap 3: the embed ran its own markdown renderer at a 0.8rem mono scale
 * while digithings.ai used the shared one, so the same answer read differently
 * on each surface. Both now render through the shared `.chat-md` grammar.
 *
 * Asserted against SERVER-rendered markup, matching this package's convention:
 * the embed must read without client JS.
 */
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { MiniMarkdown } from "./MiniMarkdown";

describe("MiniMarkdown", () => {
  it("renders through the shared chat-md grammar, not the app-local one", () => {
    const html = renderToStaticMarkup(<MiniMarkdown text="hello **world**" />);
    expect(html).toContain("chat-md");
    expect(html).not.toContain("dc-md-p");
    expect(html).toContain("<strong>world</strong>");
  });

  it("still renders GFM tables", () => {
    const html = renderToStaticMarkup(
      <MiniMarkdown text={"| a | b |\n| - | - |\n| 1 | 2 |"} />
    );
    expect(html).toContain("<table");
  });

  it("keeps a mermaid fence readable without client JS", () => {
    const html = renderToStaticMarkup(
      <MiniMarkdown text={"```mermaid\ngraph TD;A-->B;\n```"} />
    );
    expect(html).toContain("graph TD");
  });
});
