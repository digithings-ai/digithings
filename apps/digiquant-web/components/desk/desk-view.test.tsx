import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { PAGES } from "../../../../clients/digiquant-tui/src/catalog";
import { publicCatalogPages } from "./public-surface";
import { STUB_READ, presentResponse } from "../../../../clients/digiquant-tui/src/read";
import { DeskView } from "./desk-view";
import { deskPathFromSlug, deskStaticParams, isDeskPath } from "./paths";

/** `next/link` drops a trailing slash unless the Next config is loaded. */
function hasHref(html: string, href: string): boolean {
  const bare = href.replace(/\/$/, "") || "/";
  return html.includes(`href="${bare}"`) || html.includes(`href="${bare}/"`);
}

describe("terminal desk", () => {
  it("publishes every terminal page and no web-only route", () => {
    const params = deskStaticParams().map((row) => `/${row.slug.join("/")}`);
    for (const page of publicCatalogPages()) {
      expect(params).toContain(page.path);
      expect(deskPathFromSlug(page.path.split("/").filter(Boolean))).toBe(page.path);
    }
    for (const page of PAGES) {
      if (page.path === "/fx" || page.path.startsWith("/fx/")) {
        expect(params).not.toContain(page.path);
        expect(deskPathFromSlug(page.path.split("/").filter(Boolean))).toBeNull();
      }
    }
    expect(deskPathFromSlug(undefined)).toBe("/brief");
    expect(deskPathFromSlug(["markets"])).toBeNull();
    expect(deskPathFromSlug(["charts"])).toBeNull();
    expect(deskPathFromSlug(["chat"])).toBeNull();
    expect(deskPathFromSlug(["tools", "terminal"])).toBeNull();
    expect(deskPathFromSlug(["tools", "luxalgo"])).toBeNull();
    expect(deskPathFromSlug(["tools", "charts"])).toBeNull();
    expect(deskPathFromSlug(["tools", "chat"])).toBeNull();
    expect(isDeskPath("/app")).toBe(true);
    expect(isDeskPath("/app/portfolio/")).toBe(true);
    expect(isDeskPath("/")).toBe(false);
    expect(isDeskPath("/dashboard/")).toBe(false);
  });

  it("renders one block per read and withholds a stub envelope", () => {
    const stub = presentResponse("/brief", 200, { data: { nav: 99.909 } }, "fields");
    const html = renderToStaticMarkup(
      <DeskView path="/brief" reads={{ brief: stub }} />,
    );
    expect(html).toContain('aria-label="Pages"');
    expect(html).toContain('class="rail"');
    expect(html).toContain('aria-label="digiquant"');
    expect(html).toContain("desk: —");
    expect(hasHref(html, "/")).toBe(true);
    expect(html).not.toContain("luxalgo");
    expect(html).not.toContain("LuxAlgo");
    expect(html).toContain("Brief · scoreboard");
    expect(html).toContain(STUB_READ);
    expect(html).not.toContain("99.909");
    expect(html).not.toContain("204.04");
    expect(html).not.toContain("legacy_estimate");
    expect(html).not.toContain("/markets/");
    expect(html).toContain("loading…");
  });
});
