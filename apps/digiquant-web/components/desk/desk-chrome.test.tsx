import { readFileSync } from "node:fs";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { DeskAccess } from "./desk-access";
import { DeskRail } from "./desk-nav";
import {
  deskHomeHref,
  navFromDesk,
  parseManifest,
  type Manifest,
  type ManifestDesk,
} from "./desk-manifest";
import { DeskPicker } from "./desk-picker";
import { WEB_SLOTS } from "./web-slots";

const baseline: ManifestDesk = {
  id: "baseline",
  label: "Baseline",
  blurb: "The house pipeline desk.",
  access: "granted",
  pages: [
    { path: "/brief", label: "Brief", access: "granted" },
    { path: "/portfolio", label: "Portfolio", access: "granted" },
    { path: "/portfolio/holdings", label: "Holdings", access: "granted" },
    { path: "/tools/terminal", label: "Terminal", status: "soon", access: "granted" },
    { path: "/tools/charts", label: "Charts", status: "soon", access: "granted" },
    { path: "/tools/chat", label: "digichat", status: "wip", access: "granted" },
    { path: "/settings", label: "Settings", access: "granted" },
    { path: "/settings/paper", label: "Paper", access: "granted" },
    { path: "/fx/settings", label: "Settings", access: "granted" },
  ],
};

const fx: ManifestDesk = {
  id: "fx",
  label: "FX Hub",
  blurb: "FX ideas, levels and rates.",
  access: "locked",
  reason: "Requires the 12x group",
  pages: [{ path: "/fx", label: "FX Hub", access: "locked", reason: "Requires the 12x group" }],
};

const manifest: Manifest = {
  caller: { tier: "enterprise", groups: [] },
  desks: [baseline, fx],
};

describe("desk chrome", () => {
  it("keeps Terminal, Charts, and digichat and drops LuxAlgo", () => {
    expect(WEB_SLOTS.map((slot) => slot.path)).toEqual(["/tools/terminal", "/tools/charts", "/tools/chat"]);
    expect(WEB_SLOTS.map((slot) => slot.label)).toEqual(["Terminal", "Charts", "digichat"]);
    expect(JSON.stringify(WEB_SLOTS)).not.toContain("luxalgo");
  });

  it("folds manifest pages into folders and refuses a locked desk", () => {
    const groups = navFromDesk(baseline);
    const portfolio = groups.flatMap((group) => group.items).find((item) => item.path === "/portfolio");
    expect(portfolio?.children?.map((child) => child.path)).toEqual(["/portfolio/holdings"]);
    expect(groups.some((group) => group.title === "tools")).toBe(true);
    const paths = groups.flatMap((group) =>
      group.items.flatMap((item) => [item.path, ...(item.children ?? []).map((child) => child.path)]),
    );
    expect(paths).toContain("/fx/settings");
    expect(paths).toContain("/settings");
    const settings = groups.flatMap((group) => group.items).find((item) => item.path === "/settings");
    expect(settings?.children?.map((child) => child.path)).toEqual(["/settings/paper"]);
    expect(deskHomeHref(baseline)).toBe("/app/");
    expect(deskHomeHref(fx)).toBeNull();
    expect(deskHomeHref({ ...fx, access: "granted", pages: [{ path: "/fx", label: "FX Hub", access: "granted" }] })).toBe("/app/fx/");
  });

  it("does not invent desks when the manifest is missing", () => {
    expect(parseManifest(null)).toBeNull();
    expect(parseManifest({ data: {} })).toBeNull();
    expect(parseManifest({ data: { desks: [{ id: "baseline", label: "Baseline" }] } })).toBeNull();
  });

  it("renders folder paths and a locked desk that cannot be chosen", () => {
    const html = renderToStaticMarkup(
      <DeskAccess manifest={manifest}>
        <DeskRail current="/brief" />
        <DeskPicker initialOpen />
      </DeskAccess>,
    );
    const linked = (href: string) => {
      const bare = href.replace(/\/$/, "");
      return html.includes(`href="${bare}"`) || html.includes(`href="${bare}/"`);
    };
    expect(html).toContain('class="rail"');
    expect(html).toContain('id="desk-rail"');
    expect(html).toContain("~/pages");
    expect(html).toContain('aria-label="Make the sidebar smaller"');
    expect(html).toContain('aria-label="Make the sidebar larger"');
    expect(html).toContain('class="nav-row"');
    expect(html).toContain('class="nav-tri');
    expect(html).toContain('class="nav-path"');
    expect(linked("/app/portfolio/")).toBe(true);
    expect(linked("/app/tools/charts/")).toBe(true);
    expect(html).toContain(">/tools/terminal<");
    // Granted to this caller, so the rail names it. The locked FX desk stays hidden.
    expect(html).toContain(">/fx/settings<");
    expect(html).not.toContain(">/fx<");
    expect(linked("/app/settings/")).toBe(true);
    expect(html).not.toContain("luxalgo");
    expect(html).toContain("desk: Baseline");
    expect(html).not.toMatch(/fx hub|12x/i);
    expect(html).not.toContain("Requires the 12x group");
  });

  it("keeps the desk name, blurb and path in a header that scrolls instead of dropping them", () => {
    const html = renderToStaticMarkup(
      <DeskAccess manifest={manifest}>
        <DeskPicker />
      </DeskAccess>,
    );
    expect(html).toContain("desk: Baseline");
    expect(html).toContain('<span class="desk-sub">The house pipeline desk.</span>');

    const frame = readFileSync(new URL("./desk-frame.tsx", import.meta.url), "utf8");
    expect(frame).toMatch(/<div className="desk-head">\s*<DeskPicker \/>\s*<DeskCommand /);
    const css = readFileSync(new URL("../../app/globals.css", import.meta.url), "utf8");
    const head = css.slice(css.indexOf(".desk-head {"), css.indexOf("}", css.indexOf(".desk-head {")));
    expect(head).toContain("overflow-x: auto");
    expect(head).toContain("white-space: nowrap");
    expect(css).toContain(".desk-head > * { flex-shrink: 0; }");
    const narrow = css.slice(css.indexOf("@media (max-width: 759px)"), css.indexOf("@keyframes desk-page-settle"));
    expect(narrow).not.toMatch(/max-width:\s*3\.5rem|text-overflow:\s*ellipsis/);
  });

  it("keeps the draft classes and the d binding without a cursor utility", () => {    const nav = readFileSync(new URL("./desk-nav.tsx", import.meta.url), "utf8");
    const picker = readFileSync(new URL("./desk-picker.tsx", import.meta.url), "utf8");
    const css = readFileSync(new URL("../../app/globals.css", import.meta.url), "utf8");
    expect(nav).toContain('className="nav-row"');
    expect(nav).toContain('className="nav-tri');
    expect(nav).toContain('className="nav-path"');
    expect(picker).toContain('event.key === "d"');
    expect(picker).toContain("deskHomeHref");
    expect(css).toContain(".rail {");
    expect(css).toContain("--rail-w");
    expect(css).toContain('data-drawer="open"');
    expect(css).toContain(".desk-mosaic");
    expect(css).toContain(".desk-pane-body");
    expect(css).toContain(".desk-mark");
    const pane = readFileSync(new URL("./pages/pane.tsx", import.meta.url), "utf8");
    expect(pane).toContain("desk-mosaic");
    expect(pane).toContain("desk-pane-body");
    const frame = readFileSync(new URL("./desk-frame.tsx", import.meta.url), "utf8");
    expect(frame).toContain("desk-mark");
    expect(frame).toContain('aria-controls="desk-rail"');
    expect(frame).toContain("stepRailWidth");
    expect(frame).not.toMatch(/cursor-/);
    expect(css).toContain(".nav-row {");
    expect(css).toContain(".nav-tri {");
    expect(css).toContain(".nav-path {");
    expect(css).toContain(".desk-list {");
    const deskCss = css.slice(css.indexOf("Desk folder sidebar"));
    expect(`${nav}\n${picker}\n${deskCss}`).not.toMatch(/cursor-/);
    expect(deskCss).not.toMatch(/cursor\s*:/);
  });

  it("names one h1 per route and a skip link into the desk", () => {
    const shell = readFileSync(new URL("./desk-shell.tsx", import.meta.url), "utf8");
    expect(shell).toContain('className="desk-skip"');
    expect(shell).toContain('href="#desk-main"');
    expect(shell).toContain('className="desk-sr"');
    expect(shell).toContain("<h1");
    expect(shell).toContain('id="desk-main"');
    expect(shell).toContain("deskRouteLabel");
    const css = readFileSync(new URL("../../app/globals.css", import.meta.url), "utf8");
    expect(css).toContain(".desk-skip:focus-visible");
    expect(css).toContain(".desk-sr {");
  });

  it("makes scrollable pane bodies and chart hosts keyboard-focusable with a visible ring", () => {
    const view = readFileSync(new URL("./desk-view.tsx", import.meta.url), "utf8");
    expect(view).toContain("tabIndex={0}");
    expect(view).toContain('role="region"');
    const pane = readFileSync(new URL("./pages/pane.tsx", import.meta.url), "utf8");
    expect(pane).toContain("tabIndex={0}");
    const chart = readFileSync(new URL("./panel-chart.tsx", import.meta.url), "utf8");
    expect(chart).toContain("tabIndex={0}");
    const vela = readFileSync(new URL("./vela-pane.tsx", import.meta.url), "utf8");
    expect(vela).toContain("tabIndex={0}");
    expect(vela).toContain('className="vela-host');
    const css = readFileSync(new URL("../../app/globals.css", import.meta.url), "utf8");
    expect(css).toContain(".desk-pane-body:focus-visible");
    expect(css).toContain(".vela-host:focus-visible");
    expect(css).toMatch(/\.vela-host \*:not\(\.vela-callout\)\s*\{\s*border-radius:\s*0/s);
    expect(css).toContain(".vela-host button:focus-visible");
  });
});
