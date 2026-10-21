import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

/**
 * The `data-scrollbars` preference has exactly two states and both must reach
 * every scroll surface in digichat.
 *
 * `always` (the default) is the sheet's original styling: a square bar in a
 * stable gutter, so content never shifts when a list grows past the fold.
 * `auto` is the native overlay: no reserved gutter, no bar when the surface
 * fits. The failure that matters is `auto` inheriting the stable gutter from
 * the default rules — that would keep the reserved strip while claiming there
 * is none — or leaving a custom overlay bar mounted next to the native one.
 *
 * The mode attribute rides on the thread root, beside `data-thread-skin`
 * (packages/ui/src/components/chat/gallery-thread/thread.aui.tsx). So the
 * thread root is the only carrier of the mode, and a mode-dependent rule has
 * to be keyed on it. Three ways to get that wrong, all of them seen:
 *
 * - a rule that is not conditioned on the mode at all. The auto rules switch
 *   the component bars off, so an always-mode suppression that is not scoped
 *   leaves the surface with no bar at all in Chrome and Safari.
 * - a rule keyed on `:not([data-scrollbars="auto"])` on an ancestor. The app
 *   shell sets `data-thread-skin` without the mode, so that ancestor matches
 *   the negation and the always-mode rules still reach a thread that is in
 *   auto mode.
 * - a rule that reads the mode off a descendant. The mode is a property of
 *   the carrier, not of whatever is below it.
 *
 * The contract is therefore: the mode is read from the carrier, as a value,
 * in the same compound as the skin.
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

/**
 * The mode attribute must sit in the same compound as the skin selector, so
 * the element that carries the mode is the element that carries the skin.
 * The `always` rules name the skin directly; the `auto` rules keep the
 * gallery specimen frame in the `:is()` and add the mode beside it.
 */
const MODE_COMPOUND =
  /(\[data-thread-skin="digichat"\]|:is\(\.aui-theme-stage, \[data-thread-skin="digichat"\]\))\[data-scrollbars="(always|auto)"\]/;

/** Rules switched on by the `auto` mode, for the surface named by `target`. */
function autoRules(target: string): Rule[] {
  return sheet.filter(
    (rule) =>
      rule.selector.includes('[data-scrollbars="auto"]') &&
      rule.selector.includes(target),
  );
}

/** Rules switched on by the `always` mode, for the surface named by `target`. */
function alwaysRules(target: string): Rule[] {
  return sheet.filter(
    (rule) =>
      rule.selector.includes('[data-scrollbars="always"]') &&
      rule.selector.includes(target),
  );
}

/**
 * Rules that take the native bar away. Firefox reads `scrollbar-width`; Chrome
 * and Safari read the webkit pseudo. Both are the same intent, so the census
 * covers both.
 */
function nativeBarSuppressions(): Rule[] {
  return sheet.filter(
    (rule) =>
      rule.body.includes("scrollbar-width: none") ||
      (rule.body.includes("display: none") &&
        rule.selector.includes("::-webkit-scrollbar")),
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
  ["reasoning pane", '[data-slot="reasoning-text"]'],
  ["tool group content", '[data-slot="tool-group-content"]'],
];

/** The surfaces that paint a component bar in `always` mode. */
const ALWAYS_SURFACES: Array<[label: string, selector: string]> = [
  ["thread viewport", '[data-slot="aui_thread-viewport"]'],
  ["composer menu body", ".dc-composer-menu-body"],
  ["reasoning pane", '[data-slot="reasoning-text"]'],
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

  it.each(AUTO_SURFACES)("auto keeps the native bar on the %s", (_label, selector) => {
    // The native overlay bar is the whole promise of the auto mode. A styled
    // ::-webkit-scrollbar is a classic bar that reserves its own track and
    // never becomes an overlay, so auto mode styles no webkit pseudo at all.
    const matched = autoRules(selector);
    expect(matched.length).toBeGreaterThan(0);

    const bodies = matched.map((rule) => rule.body).join("\n");
    expect(bodies).not.toContain("scrollbar-width: none");
    expect(bodies).not.toContain("::-webkit-scrollbar");
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

  it("scopes the always-mode suppression so auto keeps the native bar", () => {
    // The auto rules switch the component bars off, so an always-mode
    // suppression that is not conditioned on the mode leaves the surface
    // with no bar at all in Chrome and Safari. Every suppression must name
    // the always mode.
    const suppressions = nativeBarSuppressions();
    expect(suppressions.length).toBeGreaterThan(0);
    for (const rule of suppressions) {
      expect(rule.selector).toContain('[data-scrollbars="always"]');
    }
  });

  it("reads the mode from the carrier, in the same compound as the skin", () => {
    // The mode rides on the thread root, beside the skin. A rule that reads
    // the mode from anywhere else — an ancestor that only carries the skin,
    // or a descendant — does not describe the mode of the surface.
    const modeRules = sheet.filter((rule) =>
      rule.selector.includes("data-scrollbars"),
    );
    expect(modeRules.length).toBeGreaterThan(0);
    for (const rule of modeRules) {
      expect(rule.selector).toMatch(MODE_COMPOUND);
    }
  });

  it("never reads the mode off an ancestor", () => {
    // `:not([data-scrollbars="auto"])` matches every ancestor that does not
    // carry the mode, and the app shell is such an ancestor: it sets the
    // skin without the mode. A negation would take the native bar away from
    // a thread that is in auto mode.
    for (const rule of sheet) {
      expect(rule.selector).not.toContain(":not([data-scrollbars");
    }
  });

  it("keeps the square webkit sizing out of auto mode", () => {
    // A styled ::-webkit-scrollbar is a classic bar that reserves its own
    // track, so in auto mode it would stand in for the native overlay bar
    // the mode promises. Every webkit rule therefore belongs to the always
    // mode.
    const webkit = sheet.filter((rule) =>
      rule.selector.includes("::-webkit-scrollbar"),
    );
    expect(webkit.length).toBeGreaterThan(0);
    for (const rule of webkit) {
      expect(rule.selector).toContain('[data-scrollbars="always"]');
    }
  });

  it.each(ALWAYS_SURFACES)(
    "always takes the native bar away from the %s",
    (_label, selector) => {
      // The component bar paints in always mode, so the native bar has to go:
      // Firefox on `scrollbar-width`, Chrome and Safari on the webkit pseudo.
      const matched = alwaysRules(selector);
      expect(matched.length).toBeGreaterThan(0);

      const bodies = matched.map((rule) => rule.body).join("\n");
      expect(bodies).toContain("scrollbar-width: none");
      expect(bodies).toContain("display: none");
    },
  );

  it("hides the component bars in auto mode only", () => {
    // The component bar is the always-mode bar. If it were hidden in always
    // mode too, the surface would have no bar at all.
    const hider = sheet.filter(
      (rule) =>
        rule.body.includes("display: none") &&
        (rule.selector.includes(".aui-overlay-scroll") ||
          rule.selector.includes(".dc-composer-menu-scroll")),
    );
    expect(hider.length).toBeGreaterThan(0);
    for (const rule of hider) {
      expect(rule.selector).toContain('[data-scrollbars="auto"]');
    }
  });
});
