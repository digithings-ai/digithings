import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const APP = path.resolve(fileURLToPath(new URL(".", import.meta.url)), "..");

function read(rel: string): string {
  return readFileSync(path.join(APP, rel), "utf8");
}

describe("canon chrome — nav composition", () => {
  const css = read("app/globals.css");

  it("drives the nav from the 1080px/1600px breakpoints, not a JS fit measure", () => {
    expect(css).toContain("@media (min-width: 1080px)");
    expect(css).toContain("@media (min-width: 1600px)");
    // the family map is hidden by default and re-shown at the low breakpoint,
    // so ordinary desktop widths (1280/1440) never collapse it.
    expect(css).toMatch(/\.site-nav-links \{[^}]*display: none/s);
    expect(css).toMatch(/@media \(min-width: 1080px\) \{[\s\S]*?\.site-nav-links \{[^}]*display: flex/s);
    // the old JS collapse state is gone (its selector no longer exists).
    expect(css).not.toContain(".site-nav.is-collapsed");
  });

  it("keeps the hamburger as the sub-1080px escape hatch", () => {
    const source = read("components/site-nav.tsx");
    expect(source).not.toContain("is-collapsed");
    expect(source).not.toContain("new ResizeObserver");
    expect(source).toContain("site-nav-burger");
    expect(source).toContain("SheetTrigger");
  });

  it("anchors the family map for deep links", () => {
    expect(read("components/contents-overview.tsx")).toContain('id="contents"');
  });

  it("kickers use an accessible tone, not the raw accent", () => {
    // 0.68rem tracked caps are normal text and need AA: the accent is mixed
    // toward ink, which keeps the livery identity while clearing 4.5:1.
    const tone = /color: color-mix\(in srgb, var\(--accent\) 70%, var\(--ink\)\)/;
    const section = css.match(/\.section-head \.kicker,\s*\.kicker \{[\s\S]*?\}/);
    const hero = css.match(/\.hero \.kicker \{[\s\S]*?\}/);
    expect(section?.[0]).toMatch(tone);
    expect(hero?.[0]).toMatch(tone);
  });
});

describe("canon chrome — 404 and /chatbot home", () => {
  it("ships a themed global 404 with both ways back", () => {
    // Two root layouts ((gallery) + the isolated (chatbot) shell) mean the 404
    // cannot inherit a single top-level layout, so it carries the canon's own
    // document; `next build` emits it as out/404.html for the static export.
    const file = "app/not-found.tsx";
    expect(existsSync(path.join(APP, file))).toBe(true);
    const source = read(file);
    expect(source).toContain("<html");
    expect(source).toContain("<body");
    expect(source).toContain('href="/"');
    expect(source).toContain('href="/#contents"');
    expect(source).toContain("ThemeProvider");
  });

  it("keeps the 404 off the experimental global-not-found path", () => {
    // The experimental multi-root-layout global 404 regressed prod hydration
    // (React #418) on `/`; the self-contained not-found above exports 404.html
    // without it, so the flag must stay off.
    const config = read("next.config.mjs");
    expect(config).toMatch(/output:\s*"export"/);
    expect(config).not.toMatch(/globalNotFound:\s*true/);
  });

  it("gives the isolated /chatbot shell a header link home", () => {
    const source = read("app/(chatbot)/layout.tsx");
    expect(source).toContain('href="/"');
    expect(source).toContain("chatbot-bar-home");
  });
});

describe("canon chrome — slider range coverage", () => {
  it("demonstrates the two-thumb range mode the kit API claims", () => {
    const source = read("components/controls/slider-reference.tsx");
    expect(source).toContain("RangeSliderRow");
    expect(source).toContain("useState<[number, number]>");
    // the range row passes an array value, which is what selects range mode.
    expect(source).toMatch(/value=\{value\}/);
    expect(source).toContain("range");
  });
});
