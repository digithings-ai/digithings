import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { PipelineBand } from "@/app/_bands/pipeline";

describe("PipelineBand", () => {
  const html = renderToStaticMarkup(<PipelineBand />);
  const listStart = html.indexOf("<ol");
  const listEnd = html.indexOf("</ol>");
  const list = html.slice(listStart, listEnd);

  it("renders one static banner of four pipelines", () => {
    expect(html).toContain("Four pipelines");
    expect(html).toContain('aria-label="digiquant pipelines"');
    expect(list.match(/<li\b/g)).toHaveLength(4);
    const headings = ["Research", "Investment portfolio", "Strategy building", "Trade setups"];
    let cursor = 0;
    for (const name of headings) {
      const at = list.indexOf(`>${name}<`, cursor);
      expect(at).toBeGreaterThanOrEqual(0);
      cursor = at;
    }
  });

  it("states what is done and what is still in development", () => {
    expect(list).toContain("done");
    expect(list).toContain("in development");
    expect(list).toContain("Still to come");
    expect(html).toContain("digiquant baseline research");
    expect(html).toContain("custom knowledge base");
    expect(html).toContain("12x terminal");
    expect(html).toContain("digithings");
    expect(html).toContain("digigraph");
    expect(html).toContain("digiquant baseline portfolio");
    expect(html).toContain("entry, a stop, and a target");
    expect(html).not.toMatch(/DigiQuant|DigiThings|DigiCon|Grokopedia/);
    expect(html).not.toContain("99.909");
    expect(html).not.toContain("204.04");
  });

  it("does not slide, grow a runway, or accordion a stage", () => {
    expect(html).not.toContain("motion-safe:");
    expect(html).not.toContain("100svh+220svh");
    expect(html).not.toContain("sticky");
    expect(html).not.toContain("overflow-x-auto");
    expect(html).not.toContain("snap-x");
    expect(list).not.toContain("<button");
    expect(list).not.toContain("aria-expanded");
  });
});
