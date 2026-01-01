import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

/**
 * The overlay scrollbar pointer contract (DIG-4600).
 *
 * `pointer-events` is an inherited property. The overlay track lays itself
 * over the content edge and declares `pointer-events: none` so clicks pass
 * through to the content; the thumb is a DOM child of that track, so it
 * inherits `none` and is never a pointer target — its `onPointerDown` drag
 * handler cannot fire and its `:hover` affordance never paints. The thumb
 * rule must therefore declare `pointer-events: auto` itself.
 *
 * This is a source-text test on purpose: the `packages/ui` test environment
 * is `node` with no CSS processing and no DOM, so the inherited effective
 * value cannot be computed in a unit test. The rules are parsed per
 * selector, and **every** rule that renders the element is checked, so a
 * declaration in any other rule (the composer-menu variant, a `:hover`
 * rule) cannot satisfy the check, and a duplicated block cannot carry a
 * stale value. A rule that hides the element (`display: none`) is exempt:
 * it is never rendered, so it has nothing to hit-test.
 */

const here = dirname(fileURLToPath(import.meta.url));

const css = readFileSync(join(here, "../../styles/chat-digichat.css"), "utf8");
const component = readFileSync(join(here, "overlay-scrollbar.tsx"), "utf8");

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

type Rule = { body: string; line: number };

/** Every rule whose selector list names `selector`. */
function rulesFor(selector: string): Rule[] {
  const pattern = new RegExp(`${escapeRegExp(selector)}\\s*\\{([^}]*)\\}`, "g");
  return [...css.matchAll(pattern)].map((match) => ({
    body: match[1],
    line: css.slice(0, match.index).split("\n").length,
  }));
}

/**
 * Every rule that renders `selector` must declare `pointer-events: value`.
 * A rule that hides the element is exempt.
 */
function expectPointerEvents(selector: string, value: string): void {
  const rules = rulesFor(selector);
  expect(rules.length).toBeGreaterThan(0);
  for (const rule of rules) {
    if (/(^|;)\s*display\s*:\s*none\s*;/.test(rule.body)) continue;
    const declared = rule.body.match(/pointer-events\s*:\s*([^;]+);/);
    const actual = declared ? declared[1].trim() : "";
    expect(actual, `${selector} (line ${rule.line}) must declare pointer-events: ${value}`).toBe(
      value,
    );
  }
}

describe("overlay scrollbar pointer contract", () => {
  it("keeps the overlay track pointer-transparent", () => {
    expectPointerEvents(".aui-overlay-scroll", "none");
  });

  it("makes the overlay thumb a pointer target in its own right", () => {
    // The thumb inherits the track's `none` unless it declares its own value.
    expectPointerEvents(".aui-overlay-thumb", "auto");
  });

  it("holds the composer menu scrollbar to the same contract", () => {
    expectPointerEvents(".dc-composer-menu-scroll", "none");
    expectPointerEvents(".dc-composer-menu-thumb", "auto");
  });

  it("binds the contract to the component that renders both rules", () => {
    expect(component).toContain("aui-overlay-scroll");
    expect(component).toContain("aui-overlay-thumb");
    expect(component).toContain("onPointerDown");
  });
});
