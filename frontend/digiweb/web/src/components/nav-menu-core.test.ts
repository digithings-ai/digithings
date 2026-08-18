/**
 * The dropdown's keyboard contract, unit-tested where it can be: the pure
 * key→intent map behind NavShell's roving focus. The package has no DOM
 * harness, so the *wiring* (which ref gets focused, aria-expanded flipping) is
 * covered by the SSR assertions in NavShell.render.test.tsx and by hand; the
 * arithmetic and the key coverage — the parts a refactor breaks silently — are
 * covered here.
 */
import { describe, expect, it } from "vitest";
import { navMenuIntent } from "./nav-menu-core";

const COUNT = 4; // About / Team / Security / Quality, the shipped Company group

describe("navMenuIntent", () => {
  it("walks down and wraps to the first item past the end", () => {
    expect(navMenuIntent("ArrowDown", 0, COUNT)).toEqual({ kind: "focus", index: 1 });
    expect(navMenuIntent("ArrowDown", 2, COUNT)).toEqual({ kind: "focus", index: 3 });
    expect(navMenuIntent("ArrowDown", 3, COUNT)).toEqual({ kind: "focus", index: 0 });
  });

  it("walks up and wraps to the last item past the start", () => {
    expect(navMenuIntent("ArrowUp", 3, COUNT)).toEqual({ kind: "focus", index: 2 });
    expect(navMenuIntent("ArrowUp", 0, COUNT)).toEqual({ kind: "focus", index: 3 });
  });

  it("jumps to the ends with Home and End", () => {
    expect(navMenuIntent("Home", 2, COUNT)).toEqual({ kind: "focus", index: 0 });
    expect(navMenuIntent("End", 2, COUNT)).toEqual({ kind: "focus", index: 3 });
    expect(navMenuIntent("Home", 0, COUNT)).toEqual({ kind: "focus", index: 0 });
    expect(navMenuIntent("End", 3, COUNT)).toEqual({ kind: "focus", index: 3 });
  });

  it("activates the focused item on Space — an <a href> ignores it natively", () => {
    expect(navMenuIntent(" ", 2, COUNT)).toEqual({ kind: "activate", index: 2 });
  });

  it("leaves the menu on Tab, in either direction", () => {
    // Shift is the browser's business: the panel's job is to close and put
    // focus back on the trigger so sequential navigation resumes from a
    // visible element.
    expect(navMenuIntent("Tab", 0, COUNT)).toEqual({ kind: "leave" });
    expect(navMenuIntent("Tab", 3, COUNT)).toEqual({ kind: "leave" });
  });

  it("keeps its hands off keys the menu does not own", () => {
    // Enter activates the anchor natively; Escape is NavShell's document
    // listener (one path for "close and return focus"); typeahead is not
    // implemented, so a letter must fall through rather than be swallowed.
    for (const key of ["Enter", "Escape", "a", "Z", "ArrowLeft", "ArrowRight", "PageDown"]) {
      expect(navMenuIntent(key, 1, COUNT)).toBeNull();
    }
  });

  it("clamps a stale index instead of walking out of range", () => {
    expect(navMenuIntent("ArrowDown", 9, COUNT)).toEqual({ kind: "focus", index: 0 });
    expect(navMenuIntent("ArrowUp", -3, COUNT)).toEqual({ kind: "focus", index: 3 });
    expect(navMenuIntent(" ", 9, COUNT)).toEqual({ kind: "activate", index: 3 });
  });

  it("owns no keys in an empty group", () => {
    expect(navMenuIntent("ArrowDown", 0, 0)).toBeNull();
    expect(navMenuIntent("Tab", 0, 0)).toBeNull();
  });

  it("treats a single item as both ends", () => {
    expect(navMenuIntent("ArrowDown", 0, 1)).toEqual({ kind: "focus", index: 0 });
    expect(navMenuIntent("ArrowUp", 0, 1)).toEqual({ kind: "focus", index: 0 });
    expect(navMenuIntent("End", 0, 1)).toEqual({ kind: "focus", index: 0 });
  });
});
