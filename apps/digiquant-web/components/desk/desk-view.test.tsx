import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { PAGES } from "../../../../clients/digiquant-tui/src/catalog";
import { STUB_READ, presentResponse } from "../../../../clients/digiquant-tui/src/read";
import { DeskView } from "./desk-view";
import { deskHref, deskPathFromSlug, deskStaticParams, isDeskPath } from "./paths";

describe("terminal desk", () => {
  it("publishes every terminal page and no web-only route", () => {
    const params = deskStaticParams().map((row) => `/${row.slug.join("/")}`);
    for (const page of PAGES) {
      expect(params).toContain(page.path);
      expect(deskPathFromSlug(page.path.split("/").filter(Boolean))).toBe(page.path);
    }
    expect(deskPathFromSlug(undefined)).toBe("/brief");
    expect(deskPathFromSlug(["markets"])).toBeNull();
    expect(deskPathFromSlug(["charts"])).toBeNull();
    expect(deskPathFromSlug(["chat"])).toBeNull();
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
    expect(html).toContain(deskHref("/portfolio"));
    expect(html).toContain(deskHref("/pipeline"));
    expect(html).toContain(deskHref("/fx/settings"));
    expect(html).toContain("Brief · scoreboard");
    expect(html).toContain(STUB_READ);
    expect(html).not.toContain("99.909");
    expect(html).not.toContain("204.04");
    expect(html).not.toContain("legacy_estimate");
    expect(html).not.toContain("/markets/");
    expect(html).not.toContain("/charts/");
    expect(html).not.toContain("/chat/");
    expect(html).toContain("loading…");
  });
});
