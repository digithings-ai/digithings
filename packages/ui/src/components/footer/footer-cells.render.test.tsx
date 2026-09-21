import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { FooterCells, type FooterCell } from "./FooterCells";

const CELLS: FooterCell[] = [
  { label: "GitHub", href: "https://github.com/digithings-ai", external: true },
  { label: "Docs", href: "/docs" },
  { label: "Changelog", href: "/changelog", note: "v2.3.1" },
];

describe("FooterCells", () => {
  it("renders one equal-weight cell per destination, in caller order", () => {
    const html = renderToStaticMarkup(<FooterCells cells={CELLS} />);
    expect(html).toContain('aria-label="Footer"');
    expect(html.match(/<a /g)?.length).toBe(3);
    expect(html.indexOf(">GitHub<")).toBeLessThan(html.indexOf(">Docs<"));
    expect(html.indexOf(">Docs<")).toBeLessThan(html.indexOf(">Changelog<"));
  });

  it("opens external destinations safely and leaves internal ones alone", () => {
    const html = renderToStaticMarkup(<FooterCells cells={CELLS} />);
    expect(html).toContain('target="_blank"');
    expect(html).toContain('rel="noopener noreferrer"');
    expect(html.match(/target="_blank"/g)?.length).toBe(1);
  });

  it("draws the table in hairlines, never bands", () => {
    const html = renderToStaticMarkup(<FooterCells cells={CELLS} />);
    expect(html).toContain("border-t border-hair");
    expect(html).toContain("lg:grid-cols-5");
    expect(html).toContain("lg:border-l");
    expect(html).not.toMatch(/text-(emerald|sky|amber|rose|violet|fuchsia|blue|green|red)-/);
  });

  it("renders an optional mono note per cell", () => {
    const html = renderToStaticMarkup(<FooterCells cells={CELLS} />);
    expect(html).toContain("v2.3.1");
    expect(html).toContain("text-[var(--type-meta)]");
  });

  it("renders the legal strip with meta and links", () => {
    const html = renderToStaticMarkup(
      <FooterCells
        cells={CELLS}
        meta="© 2026 digithings · open core"
        metaLinks={[{ label: "Privacy", href: "/legal/privacy" }]}
      />,
    );
    expect(html).toContain("© 2026 digithings · open core");
    expect(html).toContain('href="/legal/privacy"');
  });

  it("omits the legal strip when there is nothing to put in it", () => {
    const html = renderToStaticMarkup(<FooterCells cells={CELLS} />);
    expect(html).not.toContain("underline-offset-[3px]");
  });
});
