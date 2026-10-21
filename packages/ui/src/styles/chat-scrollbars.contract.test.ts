import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

/**
 * The `data-scrollbars` preference has exactly two states and both must reach
 * every scroll surface in digichat.
 *
 * `always` (the default, attribute absent) is the sheet's original styling: a
 * square bar in a stable gutter, so content never shifts when a list grows
 * past the fold. `auto` is the native overlay: no reserved gutter, no bar when
 * the surface fits. The failure that matters is `auto` inheriting the stable
 * gutter from the default rules — that would keep the reserved strip while
 * claiming there is none — or leaving a custom overlay bar mounted next to
 * the native one.
 */

const here = dirname(fileURLToPath(import.meta.url));

const css = readFileSync(join(here, "chat-digichat.css"), "utf8");

/** Comments stripped, so a selector named in prose cannot satisfy a test. */
function stripComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "");
}

type Rule = { selector: string; body: string };

/** Leaf rules only: a body containing no braces. Enough for these assertions. */
function rules(source: string): Rule[] {
  const found: Rule[] = [];
  const re = /([^{}]+)\{([^{}]*)\}/g;
  let match = re.exec(source);
  while (match) {
    found.push({ selector: match[1], body: match[2] });
    match = re.exec(source);
  }
  return found;
}

const sheet = rules(stripComments(css));

/** Rules that are switched on by `[data-scrollbars="auto"]` and touch `target`. */
function autoRules(target: string): Rule[] {
  return sheet.filter(
    (rule) => rule.selector.includes('[data-scrollbars="auto"]') && rule.selector.includes(target),
  );
}

const AUTO_SURFACES: Array<[label: string, selector: string]> = [
  ["thread viewport", '[data-slot="aui_thread-viewport"]'],
  ["composer textarea", ".aui-composer-input"],
  ["composer menu body", ".dc-composer-menu-body"],
  ["slash palette list", '[data-slot="composer-trigger-popover-items"]'],
  ["tool fallback dump", '[data-slot="tool-fallback-dump"]'],
  ["tool fallback args", ".aui-tool-fallback-args-value"],
  ["tool fallback result", ".aui-tool-fallback-result-content"],
];

describe("data-scrollbars contract", () => {
  it.each(AUTO_SURFACES)("auto drops the reserved gutter on the %s", (_label, selector) => {
    const matched = autoRules(selector);
    // A zero-length match would otherwise read as a pass.
    expect(matched.length).toBeGreaterThan(0);

    const bodies = matched.map((rule) => rule.body).join("\n");
    expect(bodies).toContain("scrollbar-gutter: auto");
    expect(bodies).not.toContain("scrollbar-gutter: stable");
  });

  it("auto keeps a thin bar and lets the surface scroll on overflow", () => {
    for (const [, selector] of AUTO_SURFACES) {
      const bodies = autoRules(selector)
        .map((rule) => rule.body)
        .join("\n");
      expect(bodies).toContain("overflow-y: auto");
      expect(bodies).toContain("scrollbar-width: thin");
    }
  });

  it("always is still the unreserved default, gutter and all", () => {
    const base = sheet.filter(
      (rule) =>
        rule.selector.includes(".dc-composer-menu-body") &&
        !rule.selector.includes("data-scrollbars"),
    );
    expect(base.length).toBeGreaterThan(0);

    const bodies = base.map((rule) => rule.body).join("\n");
    expect(bodies).toContain("overflow-y: scroll");
    expect(bodies).toContain("scrollbar-gutter: stable");
  });

  it("never turns the thread viewport horizontal", () => {
    const viewport = sheet.filter(
      (rule) =>
        rule.selector.includes('[data-slot="aui_thread-viewport"]') &&
        rule.body.includes("overflow-x"),
    );
    expect(viewport.length).toBeGreaterThan(0);
    for (const rule of viewport) {
      expect(rule.body).toContain("overflow-x: hidden");
      expect(rule.body).not.toContain("overflow-x: auto");
      expect(rule.body).not.toContain("overflow-x: scroll");
    }
  });

  it("hides both custom overlay bars under auto so there is no double bar", () => {
    for (const target of [".aui-overlay-scroll", ".dc-composer-menu-scroll"]) {
      const matched = autoRules(target);
      expect(matched.length).toBeGreaterThan(0);
      expect(matched.map((rule) => rule.body).join("\n")).toContain("display: none");
    }
  });

  it("reaches the portalled palette list through the document", () => {
    const matched = autoRules('[data-slot="composer-trigger-popover-items"]');
    expect(matched.length).toBeGreaterThan(0);
    expect(matched.some((rule) => rule.selector.includes("html:has("))).toBe(true);
  });
});
