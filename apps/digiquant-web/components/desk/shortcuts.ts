/**
 * The digiquant app keyboard map: single source for the handler in DeskFrame,
 * the `?` overlay and docs/surfaces/digiquant-app-shortcuts.md.
 * Ported from the retired apps/digiquant-app (lib/shortcuts.ts); keys match the
 * digiquant TUI (clients/digiquant-tui/src/app.tsx) where the TUI has one.
 *  `Tab` moves between blocks and controls in DOM order (owner ruling
 *  2026-10-12 make_it_work): blocks are focusable sections, so native Tab
 *  reaches them with no custom key handler.
 */
export type Shortcut = { keys: string; does: string; tui?: string };

export const SHORTCUTS: Shortcut[] = [
  { keys: "/  or  ⌘K", does: "Go to any page (command line)", tui: "/" },
  { keys: "↑ ↓ Enter", does: "Move / open in the command list", tui: "↑ ↓ Enter" },
  { keys: "d", does: "Switch desk (↑ ↓ Enter; locked desks show what unlocks them)", tui: "d" },
  { keys: "n", does: "Focus the page rail (opens the drawer on a phone)" },
  { keys: "rail ↑ ↓ / j k", does: "Walk the page tree; Enter loads the focused page", tui: "↑ ↓ / j k" },
  { keys: "rail → ← / l h", does: "Open / close a folder, step into it or back to its parent", tui: "→ ← / l h" },
  { keys: "Home / End", does: "First / last page in the rail" },
  { keys: "[  ]", does: "Narrower / wider page rail", tui: "[ ]" },
  { keys: "Tab", does: "Move between blocks and controls", tui: "Tab" },
  { keys: "Esc", does: "Close menu, list, drawer or this help", tui: "Esc" },
  { keys: "?", does: "Show / hide shortcuts" },
];

/** True when a key event belongs to a text field and must not trigger shortcuts. */
export function isTyping(target: EventTarget | null): boolean {
  return (
    (typeof HTMLInputElement !== "undefined" && target instanceof HTMLInputElement) ||
    (typeof HTMLTextAreaElement !== "undefined" && target instanceof HTMLTextAreaElement) ||
    (typeof HTMLSelectElement !== "undefined" && target instanceof HTMLSelectElement) ||
    (typeof HTMLElement !== "undefined" && target instanceof HTMLElement && target.isContentEditable)
  );
}
