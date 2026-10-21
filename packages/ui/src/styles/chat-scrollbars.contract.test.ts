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
 * (`packages/ui/src/components/chat/gallery-thread/thread.aui.tsx` writes
 * both on the same `ThreadPrimitive.Root`). The thread root is therefore the
 * only carrier of the mode, and every mode-dependent rule has to be keyed on
 * it, in the same compound as the skin. Five ways to get that wrong, all of
 * them seen:
 *
 * - a rule that is not conditioned on the mode at all. The auto rules switch
 *   the component bars off, so an always-mode suppression that is not scoped
 *   leaves the surface with no bar at all in Chrome and Safari, and in
 *   Firefox it takes the native bar away from a thread that is in auto mode.
 * - a rule keyed on `:not([data-scrollbars="auto"])` on an ancestor. The app
 *   shell sets `data-thread-skin` without the mode, so that ancestor matches
 *   the negation and the always-mode rules still reach a thread that is in
 *   auto mode.
 * - a rule that reads the mode off a descendant. The mode is a property of the
 *   carrier, not of whatever is below it.
 * - a rule that reads the mode off the document (`html:has(...)`, or any
 *   other spelling of it). A page can carry a thread in each mode at once,
 *   and the document-level form hands the always treatment to the auto
 *   thread's palette.
 * - a selector list that mixes one conditioned selector with an unconditioned
 *   one. The condition on half a group styles the other half too, so every
 *   selector of a rule is audited on its own.
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

/**
 * Leaf rules, with at-rule blocks unwrapped.
 *
 * A brace-aware walk, not a regex: a rule can carry a list of selectors, and
 * each one of them has to be audited on its own, because a condition on half
 * a group styles the other half too. Rules inside an at-rule are audited as
 * well — the at-rule condition is not modelled, so the inner rule is read as
 * if it always applies, which is the stricter reading. CSS nesting is refused
 * loudly rather than silently mis-parsed.
 */
function rules(source: string): Rule[] {
  const found: Rule[] = [];
  let index = 0;
  while (index < source.length) {
    const open = source.indexOf("{", index);
    if (open === -1) break;
    const prelude = source.slice(index, open).trim();
    let depth = 1;
    let cursor = open + 1;
    while (cursor < source.length && depth > 0) {
      const char = source[cursor];
      if (char === "{") depth += 1;
      else if (char === "}") depth -= 1;
      cursor += 1;
    }
    const body = source.slice(open + 1, cursor - 1);
    if (prelude.startsWith("@")) {
      found.push(...rules(body));
    } else {
      if (body.includes("{")) {
        throw new Error(
          `the sheet nests rules near "${prelude.slice(0, 60)}": the contract parser has to handle it`,
        );
      }
      found.push({ selector: prelude, body });
    }
    index = cursor;
  }
  return found;
}

const sheet = rules(stripComments(css));

/** The selectors of a rule, one by one. */
function selectorsOf(rule: Rule): string[] {
  return rule.selector
    .split(",")
    .map((selector) => selector.trim())
    .filter(Boolean);
}

/** Whether a selector names the surface, as a whole compound token. */
function namesSurface(selector: string, target: string): boolean {
  let at = selector.indexOf(target);
  while (at !== -1) {
    const next = selector[at + target.length];
    if (next === undefined || !/[A-Za-z0-9_-]/.test(next)) return true;
    at = selector.indexOf(target, at + 1);
  }
  return false;
}

/**
 * The declarations of a rule, with the spacing normalised, so
 * `scrollbar-width:none` reads the same as `scrollbar-width: none`.
 */
function declarations(rule: Rule): string {
  return rule.body.replace(/\s*:\s*/g, ": ");
}

/**
 * The carrier: the thread root. The skin and the mode sit in the same
 * compound on that one element, so a rule that names the mode names the
 * carrier with it.
 */
const CARRIER = '[data-thread-skin="digichat"]';

/** The mode, as a value, in the same compound as the skin. */
const MODE_COMPOUND = /\[data-thread-skin="digichat"\]\[data-scrollbars="(always|auto)"\]/;

/** Rules switched on by `mode`, for the surface named by `target`. */
function modeRules(mode: "always" | "auto", target: string): Rule[] {
  return sheet.filter((rule) =>
    selectorsOf(rule).some(
      (selector) =>
        selector.includes(`[data-scrollbars="${mode}"]`) &&
        namesSurface(selector, target),
    ),
  );
}

/** The selectors of the rules switched on by `mode`, for the surface. */
function modeSelectors(mode: "always" | "auto", target: string): string[] {
  return sheet.flatMap((rule) =>
    selectorsOf(rule).filter(
      (selector) =>
        selector.includes(`[data-scrollbars="${mode}"]`) &&
        namesSurface(selector, target),
    ),
  );
}

/** Rules switched on by the `auto` mode, for the surface named by `target`. */
function autoRules(target: string): Rule[] {
  return modeRules("auto", target);
}

/** Rules switched on by the `always` mode, for the surface named by `target`. */
function alwaysRules(target: string): Rule[] {
  return modeRules("always", target);
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
  ["slash palette list", '[data-slot="composer-trigger-popover-items"]'],
];

/** The surfaces the sheet gives a square webkit bar in `always` mode. */
const ALWAYS_SIZED_SURFACES: Array<[label: string, selector: string]> = [
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

/**
 * The surfaces that have no component bar: they keep the native bar in
 * always mode, so the always-mode suppression must leave them alone.
 */
const ALWAYS_NATIVE_SURFACES: Array<[label: string, selector: string]> = [
  ["composer textarea", ".aui-composer-input"],
  ["tool fallback dump", '[data-slot="tool-fallback-dump"]'],
  ["tool fallback args", ".aui-tool-fallback-args-value"],
  ["tool fallback result", ".aui-tool-fallback-result-content"],
  ["tool group content", '[data-slot="tool-group-content"]'],
];

describe("data-scrollbars contract", () => {
  it.each(AUTO_SURFACES)("auto drops the reserved gutter on the %s", (_label, selector) => {
    const matched = autoRules(selector);
    // A zero-length match would otherwise read as a pass.
    expect(matched.length).toBeGreaterThan(0);

    const bodies = matched.map(declarations).join("\n");
    expect(bodies).toContain("scrollbar-gutter: auto");
    expect(bodies).not.toContain("scrollbar-gutter: stable");
  });

  it("auto keeps a thin bar and lets the surface scroll on overflow", () => {
    for (const [, selector] of AUTO_SURFACES) {
      const bodies = autoRules(selector)
        .map(declarations)
        .join("\n");
      expect(bodies).toContain("overflow-y: auto");
      expect(bodies).toContain("scrollbar-width: thin");
    }
  });

  it.each(AUTO_SURFACES)("auto keeps the native bar on the %s", (_label, selector) => {
    // The native overlay bar is the whole promise of the auto mode. A styled
    // ::-webkit-scrollbar is a classic bar that reserves its own track and
    // never becomes an overlay, so auto mode styles no webkit pseudo at all,
    // and nothing in it takes the native bar away.
    const matched = autoRules(selector);
    expect(matched.length).toBeGreaterThan(0);

    for (const rule of matched) {
      expect(declarations(rule)).not.toContain("scrollbar-width: none");
      for (const selector of selectorsOf(rule)) {
        expect(selector).not.toContain("::-webkit-scrollbar");
      }
    }
  });

  it("always is still the unreserved default, gutter and all", () => {
    const base = sheet.filter(
      (rule) =>
        rule.selector.includes(".dc-composer-menu-body") &&
        !rule.selector.includes("data-scrollbars"),
    );
    expect(base.length).toBeGreaterThan(0);

    const bodies = base.map(declarations).join("\n");
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
      expect(matched.map(declarations).join("\n")).toContain("display: none");
    }
  });

  it("scopes the always-mode suppression so auto keeps the native bar", () => {
    // The auto rules switch the component bars off, so an always-mode
    // suppression that is not conditioned on the mode leaves the surface with
    // no bar at all in Chrome and Safari, and in Firefox it takes the native
    // bar away from a thread that is in auto mode. Every suppression must
    // name the always mode — and every selector of the rule that carries it,
    // because a group styles all of its selectors.
    const suppressions = sheet.flatMap((rule) =>
      selectorsOf(rule).filter(
        (selector) =>
          declarations(rule).includes("scrollbar-width: none") ||
          (declarations(rule).includes("display: none") &&
            selector.includes("::-webkit-scrollbar")),
      ),
    );
    expect(suppressions.length).toBeGreaterThan(0);
    for (const selector of suppressions) {
      expect(selector).toContain('[data-scrollbars="always"]');
    }
  });

  it("reads the mode from the carrier, in the same compound as the skin", () => {
    // The mode rides on the thread root, beside the skin. A rule that reads
    // the mode from anywhere else — an ancestor that only carries the skin,
    // a descendant, or the document — does not describe the mode of the
    // surface it styles.
    const conditioned = sheet.flatMap((rule) =>
      selectorsOf(rule).filter((selector) => selector.includes("data-scrollbars")),
    );
    expect(conditioned.length).toBeGreaterThan(0);
    for (const selector of conditioned) {
      expect(selector).toMatch(MODE_COMPOUND);
    }
  });

  it("never reads the mode off an ancestor", () => {
    // `:not([data-scrollbars="auto"])` matches every ancestor that does not
    // carry the mode, and the app shell is such an ancestor: it sets the
    // skin without the mode. A negation would take the native bar away from
    // a thread that is in auto mode.
    for (const rule of sheet) {
      for (const selector of selectorsOf(rule)) {
        expect(selector).not.toContain(":not([data-scrollbars");
      }
    }
  });

  it("never reads the mode off the document", () => {
    // `html:has(...)` matches the whole document, so a page that carries a
    // thread in each mode hands one thread's palette the other mode's
    // treatment. The mode is read from the carrier, by ancestry. Any spelling
    // of the document form counts: the spelling is not the contract.
    for (const rule of sheet) {
      for (const selector of selectorsOf(rule)) {
        expect(selector).not.toMatch(/:has\([^)]*data-scrollbars/);
      }
    }
  });

  it("keeps the square webkit sizing out of auto mode", () => {
    // A styled ::-webkit-scrollbar is a classic bar that reserves its own
    // track, so in auto mode it would stand in for the native overlay bar
    // the mode promises. Every webkit rule therefore belongs to the always
    // mode — every selector of it, because a group styles all of them.
    const webkit = sheet.flatMap((rule) =>
      selectorsOf(rule).filter((selector) =>
        selector.includes("::-webkit-scrollbar"),
      ),
    );
    expect(webkit.length).toBeGreaterThan(0);
    for (const selector of webkit) {
      expect(selector).toContain('[data-scrollbars="always"]');
    }
  });

  it.each(ALWAYS_SIZED_SURFACES)(
    "always gives the %s its square webkit bar",
    (_label, selector) => {
      // The square bar is the always look, and it is styled per surface:
      // 10px on the thread, 6px in the composer and the menu, 4px in the
      // deepest scroll. Dropping one of those groups would leave the surface
      // with the platform bar in always mode, next to its component bar.
      const sized = sheet.filter(
        (rule) =>
          /(^|;)\s*width\s*:/.test(declarations(rule)) &&
          selectorsOf(rule).some(
            (candidate) =>
              candidate.includes('[data-scrollbars="always"]') &&
              candidate.includes("::-webkit-scrollbar") &&
              namesSurface(candidate, selector),
          ),
      );
      expect(sized.length).toBeGreaterThan(0);
    },
  );

  it.each(ALWAYS_SURFACES)(
    "always takes the native bar away from the %s",
    (_label, selector) => {
      // The component bar paints in always mode, so the native bar has to go:
      // Firefox on `scrollbar-width`, Chrome and Safari on the webkit pseudo.
      const matched = alwaysRules(selector);
      expect(matched.length).toBeGreaterThan(0);

      const bodies = matched.map(declarations).join("\n");
      expect(bodies).toContain("scrollbar-width: none");
      expect(bodies).toContain("display: none");
    },
  );

  it.each(ALWAYS_NATIVE_SURFACES)(
    "always keeps the native bar on the %s",
    (_label, selector) => {
      // The converse of the rule above: a surface with no component bar keeps
      // the native one, so the always-mode suppression must not reach it. If
      // it did, the surface would have no bar at all in always mode.
      const suppressed = alwaysRules(selector).filter((rule) =>
        declarations(rule).includes("scrollbar-width: none"),
      );
      expect(suppressed).toHaveLength(0);
    },
  );

  it("hides the component bars in auto mode only", () => {
    // The component bar is the always-mode bar. If it were hidden in always
    // mode too, the surface would have no bar at all.
    const hiding = sheet.flatMap((rule) =>
      selectorsOf(rule).filter(
        (selector) =>
          (selector.includes(".aui-overlay-scroll") ||
            selector.includes(".dc-composer-menu-scroll")) &&
          declarations(rule).includes("display: none"),
      ),
    );
    expect(hiding.length).toBeGreaterThan(0);
    for (const selector of hiding) {
      expect(selector).toContain('[data-scrollbars="auto"]');
    }
  });

  it("keys every mode rule on the carrier, never on the skin alone", () => {
    // The skin alone is not the mode: the app shell sets `data-thread-skin`
    // without the mode, so a rule keyed on the skin alone reaches a thread
    // that is in the other mode.
    for (const rule of sheet) {
      for (const selector of selectorsOf(rule)) {
        if (!selector.includes("data-scrollbars")) continue;
        expect(selector).toContain(CARRIER);
      }
    }
  });
});
