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
    expect(paths).not.toContain("/settings");
    expect(paths).not.toContain("/settings/paper");
    expect(deskHomeHref(baseline)).toBe("/app/brief/");
    expect(deskHomeHref(fx)).toBeNull();
    expect(deskHomeHref({ ...fx, access: "granted", pages: [{ path: "/fx", label: "FX Hub", access: "granted" }] })).toBeNull();
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
    expect(html).toContain("~/pages");
    expect(html).toContain('class="nav-row"');
    expect(html).toContain('class="nav-tri');
    expect(html).toContain('class="nav-path"');
    expect(linked("/app/portfolio/")).toBe(true);
    expect(linked("/app/tools/charts/")).toBe(true);
    expect(html).toContain(">/tools/terminal<");
    expect(html).not.toContain(">/fx/settings<");
    expect(html).not.toContain(">/fx<");
    expect(html).not.toContain(">/settings<");
    expect(html).not.toContain(">/settings/paper<");
    expect(html).not.toContain('href="/app/settings"');
    expect(html).not.toContain('href="/app/settings/');
    expect(html).not.toContain("luxalgo");
    expect(html).toContain("desk: Baseline");
    expect(html).not.toMatch(/fx hub|12x/i);
    expect(html).not.toContain("Requires the 12x group");
  });

  it("keeps the draft classes and the d binding without a cursor utility", () => {
    const nav = readFileSync(new URL("./desk-nav.tsx", import.meta.url), "utf8");
    const picker = readFileSync(new URL("./desk-picker.tsx", import.meta.url), "utf8");
    const css = readFileSync(new URL("../../app/globals.css", import.meta.url), "utf8");
    expect(nav).toContain('className="nav-row"');
    expect(nav).toContain('className="nav-tri');
    expect(nav).toContain('className="nav-path"');
    expect(picker).toContain('event.key === "d"');
    expect(picker).toContain("deskHomeHref");
    expect(css).toContain(".rail {");
    expect(css).toContain(".nav-row {");
    expect(css).toContain(".nav-tri {");
    expect(css).toContain(".nav-path {");
    expect(css).toContain(".desk-list {");
    const deskCss = css.slice(css.indexOf("Desk folder sidebar"));
    expect(`${nav}\n${picker}\n${deskCss}`).not.toMatch(/cursor-/);
    expect(deskCss).not.toMatch(/cursor\s*:/);
  });
});
