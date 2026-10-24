import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { publicCatalogPages } from "./public-surface";
import { STUB_READ, presentResponse } from "digiquant-tui/read";
import { DeskReadout, DeskView } from "./desk-view";
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
      // The brief IS the app: served at /app, /app/brief redirects there.
      if (page.path === "/brief") {
        expect(params).not.toContain("/brief");
        expect(deskPathFromSlug(["brief"])).toBeNull();
        continue;
      }
      expect(params).toContain(page.path);
      expect(deskPathFromSlug(page.path.split("/").filter(Boolean))).toBe(page.path);
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

describe("fx desk panes", () => {
  const OK = { status: "ok" as const, lines: ["source  core:macro_series_observations"], asOf: "2026-09-24" };

  it("paints the rates panes as blocks instead of one text line", () => {
    const html = renderToStaticMarkup(
      <DeskReadout
        path="/fx/rates"
        reads={{ "rt-curve": OK, "rt-summary": OK, "rt-watchlist": OK, "rt-theses": OK }}
        data={{
          "rt-curve": {
            curve: [
              { tenor: "2Y", yield_pct: 4.1, day_change: 0.03 },
              { tenor: "10Y", yield_pct: 4.35, day_change: -0.02 },
            ],
            spreads: [{ label: "10Y-2Y", bp: 25, day_bp: -5 }],
          },
          "rt-summary": { run_date: "2026-09-24", watchlist: { marks_available: 4 }, budget: {} },
          "rt-watchlist": { names: [] },
          "rt-theses": { theses: [], counts: {} },
        }}
      />,
    );
    // The curve keeps the table/chart toggle; nothing paints the raw lines.
    expect(html).toContain('data-panel="rt-curve"');
    expect(html).toContain('aria-label="Rates · curve view"');
    expect(html).toContain(">Table<");
    expect(html).toContain(">Chart<");
    expect(html).toContain("Marks");
    expect(html).toContain("No watchlist names in this read.");
    expect(html).toContain("No rates theses in this read.");
    // The read's provenance survives the block that replaced its text face.
    expect(html).toContain("source  core:macro_series_observations");
  });

  it("paints an FX pane with no panel shape as a sortable table", () => {
    const html = renderToStaticMarkup(
      <DeskReadout
        path="/fx/ideas"
        reads={{ "fx-ideas": OK }}
        data={{
          "fx-ideas": {
            ideas: [
              { rank: 1, pair: "USDJPY", bias: "long", horizon: "1w", invalidation: 151.2, status: "open", thread: "Carry still pays." },
            ],
          },
        }}
      />,
    );
    expect(html).toContain("Carry still pays.");
    expect(html).toContain("151.20");
    expect(html).toContain(">rank<span");
    expect(html).toContain('aria-sort="none"');
  });

  it("withholds an ok read that carried no payload, and names that", () => {
    const html = renderToStaticMarkup(<DeskReadout path="/fx/rates" reads={{ "rt-curve": OK }} />);
    expect(html).toContain('data-state="withheld"');
    expect(html).toContain("no data object");
    expect(html).not.toContain("undefined");
  });

  it("leaves a pane without a block on the read's own lines", () => {
    const html = renderToStaticMarkup(
      <DeskReadout
        path="/portfolio/holdings"
        reads={{ holdings: { status: "ok", lines: ["ticker  AAA"], asOf: null } }}
      />,
    );
    expect(html).toContain("ticker  AAA");
  });
});
