import { readFileSync } from "node:fs";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { DeskCommand } from "./desk-command";
import { searchDeskPages } from "./desk-command-search";
import { publicCatalogPages } from "./public-surface";
import { deskHref } from "./paths";

describe("desk slash field", () => {
  it("renders the idle path field", () => {
    const html = renderToStaticMarkup(createElement(DeskCommand, { pathname: "/app/brief/" }));
    expect(html).toContain('class="cmd"');
    expect(html).toContain('aria-label="Go to page"');
    expect(html).toContain('value="/app/brief/"');
  });

  it("lists OpenTUI pages plus Terminal, Charts, and digichat", () => {
    const hits = searchDeskPages("");
    expect(hits.map((hit) => hit.path)).toEqual([
      ...publicCatalogPages().map((page) => page.path),
      "/tools/terminal",
      "/tools/charts",
      "/tools/chat",
    ]);
    expect(hits.some((hit) => hit.path === "/fx" || hit.path.startsWith("/fx/"))).toBe(false);
    expect(JSON.stringify(hits)).not.toMatch(/fx hub|12x/i);
    expect(hits.map((hit) => hit.href)).toEqual(hits.map((hit) => deskHref(hit.path)));
    expect(hits.some((hit) => hit.path.includes("luxalgo") || hit.label === "LuxAlgo")).toBe(false);
  });

  it("filters on path, label, and desk href", () => {
    expect(searchDeskPages("portfolio").map((hit) => hit.path)).toEqual([
      "/portfolio",
      "/portfolio/holdings",
      "/portfolio/attribution",
      "/portfolio/ledger",
      "/portfolio/theses",
      "/portfolio/tearsheet",
    ]);
    expect(searchDeskPages("charts")[0]?.href).toBe("/app/tools/charts/");
    expect(searchDeskPages("digichat")[0]?.href).toBe("/app/tools/chat/");
    expect(searchDeskPages("/app/tools/terminal/").map((hit) => hit.label)).toEqual(["Terminal"]);
    expect(searchDeskPages("luxalgo")).toEqual([]);
    expect(searchDeskPages("fx")).toEqual([]);
    expect(searchDeskPages("12x")).toEqual([]);
  });

  it("keeps the draft field classes and the slash binding", () => {
    const view = readFileSync(new URL("./desk-command.tsx", import.meta.url), "utf8");
    const css = readFileSync(new URL("../../app/globals.css", import.meta.url), "utf8");
    expect(view).toContain('className="cmd"');
    expect(view).toContain('className="cmd-in"');
    expect(view).toContain('className="cmd-list"');
    expect(view).toContain('e.key === "/"');
    expect(view).toContain("e.metaKey || e.ctrlKey");
    expect(view).not.toContain("luxalgo");
    expect(view).not.toMatch(/cursor-/);
    expect(css).toContain(".cmd-in:focus");
    expect(css).toContain(".cmd-list");
    expect(css).not.toMatch(/\.cmd[^\n]*cursor\s*:/);
  });

  it("opens the page list over the desk", () => {
    const frame = readFileSync(new URL("./desk-frame.tsx", import.meta.url), "utf8");
    const css = readFileSync(new URL("../../app/globals.css", import.meta.url), "utf8");
    expect(frame).toContain("relative z-50");
    expect(frame).toContain("h-8");
    expect(css).toMatch(/\.cmd-list\s*\{[^}]*position:\s*absolute/s);
    expect(css).not.toMatch(/\.cmd-list\s*\{[^}]*position:\s*static/s);
  });
});