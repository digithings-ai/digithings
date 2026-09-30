import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { CardRail } from "./CardRail";

function render() {
  return renderToStaticMarkup(
    <CardRail ariaLabel="Strategy tearsheets" header={<h2>Tearsheets</h2>}>
      <a href="/a">Card A</a>
      <a href="/b">Card B</a>
      <a href="/c">Card C</a>
    </CardRail>,
  );
}

describe("CardRail", () => {
  it("is a native scroll-snap list with one item per child, in order", () => {
    const html = render();
    expect(html).toContain('role="list"');
    expect(html).toContain('aria-label="Strategy tearsheets"');
    expect(html).toContain("snap-x");
    expect(html).toContain("overflow-x-auto");
    expect(html.match(/role="listitem"/g)?.length).toBe(3);
    expect(html.indexOf("Card A")).toBeLessThan(html.indexOf("Card B"));
    expect(html.indexOf("Card B")).toBeLessThan(html.indexOf("Card C"));
  });

  it("renders prev / next buttons that start at the leading edge", () => {
    const html = render();
    expect(html).toContain('aria-label="Previous card"');
    expect(html).toContain('aria-label="Next card"');
    // atStart on first paint: prev disabled, next enabled
    expect(html.match(/aria-label="Previous card"[^>]*disabled=""|disabled=""[^>]*aria-label="Previous card"/)).toBeTruthy();
    expect(html.indexOf("Tearsheets")).toBeLessThan(html.indexOf("Previous card"));
  });

  it("marks the first card active and keeps the cards keyboard reachable", () => {
    const html = render();
    expect(html.match(/data-active="true"/g)?.length).toBe(1);
    expect(html).toContain('href="/a"');
    expect(html).toContain('tabindex="0"');
  });

  it("fades the edges through tokens, never a raw colour", () => {
    const html = render();
    expect(html).toContain("var(--ink)");
    expect(html).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
    expect(html).not.toMatch(/rgba?\(/);
  });
});
