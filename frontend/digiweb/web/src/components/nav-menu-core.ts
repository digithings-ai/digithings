/**
 * Pure key→intent mapping for a NavShell dropdown's roving focus
 * (see ./NavShell.tsx). Framework- and DOM-free, in the shape of
 * ../motion/scrolly-core.ts, so the part that breaks silently under a
 * refactor — the wrap arithmetic and which keys the panel owns at all — is
 * unit-testable in a package that has no DOM harness.
 *
 * The grammar is the menu-button pattern's core, not the whole WAI-ARIA APG
 * `menu` pattern: there is no character typeahead. Enter is deliberately absent
 * from the map — the items are real `<a href>` anchors, so the browser
 * activates them natively; Space is here precisely because an anchor ignores it
 * (it would scroll the page instead). Escape is absent too: NavShell handles it
 * on a document listener, so it closes from wherever focus sits.
 */

/** What a key press means inside an open menu panel. */
export type NavMenuIntent =
  /** Move roving focus to `index` — already wrapped into range. */
  | { kind: "focus"; index: number }
  /** Activate the item at `index` (Space; Enter needs no help). */
  | { kind: "activate"; index: number }
  /** Leave the menu: hand focus back to the trigger, then close. */
  | { kind: "leave" }
  /** Not the menu's key — let it through untouched. */
  | null;

/**
 * Map a key press in an open panel of `count` items, with roving focus at
 * `current`, to the panel's intent. `current` is clamped rather than trusted,
 * so a stale index (items changed under an open menu) still yields a real one.
 */
export function navMenuIntent(key: string, current: number, count: number): NavMenuIntent {
  if (count <= 0) return null;
  const last = count - 1;
  const at = Math.min(Math.max(current, 0), last);
  switch (key) {
    case "ArrowDown":
      return { kind: "focus", index: at >= last ? 0 : at + 1 };
    case "ArrowUp":
      return { kind: "focus", index: at <= 0 ? last : at - 1 };
    case "Home":
      return { kind: "focus", index: 0 };
    case "End":
      return { kind: "focus", index: last };
    case " ":
      return { kind: "activate", index: at };
    case "Tab":
      return { kind: "leave" };
    default:
      return null;
  }
}
