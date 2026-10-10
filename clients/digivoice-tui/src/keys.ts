/**
 * digivoice key map. One reducer, one state, one effect per key, mirroring the
 * digichat-tui pattern: app.tsx paints state, the reducer decides.
 */
export type Screen = "home" | "models" | "features" | "hotkeys" | "hardware" | "review" | "doctor" | "history";

export type UiState = {
  screen: Screen;
  menuIndex: number;
  rowIndex: number;
  note: string;
};

export type KeyIn = { name?: string; ctrl?: boolean; sequence?: string };

export type RowKind = "edit" | "toggle" | "cycle" | "back" | "read";
export type Row = { id: string; kind: RowKind };

export type KeyCtx = {
  menu: readonly string[];
  rows: readonly Row[];
};

export type KeyEffect =
  | { type: "quit" }
  | { type: "open"; screen: Screen }
  | { type: "back" }
  | { type: "edit"; id: string }
  | { type: "toggle"; id: string }
  | { type: "cycle"; id: string; delta: number }
  | { type: "read"; id: string }
  | { type: "reload" };

export type KeyResult = { state: UiState; effect: KeyEffect | null };

export const INITIAL_UI: UiState = { screen: "home", menuIndex: 0, rowIndex: 0, note: "" };

/** Home menu index -> screen. Index 6 is Quit, handled as an effect. */
export const MENU_SCREENS: readonly (Screen | "quit")[] = [
  "models",
  "features",
  "hotkeys",
  "hardware",
  "review",
  "doctor",
  "quit",
];

export function nextIndex(index: number, delta: number, length: number): number {
  if (length <= 0) return 0;
  return ((index + delta) % length + length) % length;
}

export function reduceKey(state: UiState, key: KeyIn, ctx: KeyCtx): KeyResult {
  if (key.ctrl) return { state, effect: null };
  const name = key.name ?? "";
  const atHome = state.screen === "home";

  if (name === "q") return { state, effect: { type: "quit" } };
  if (name === "r") return { state: { ...state, note: "reloading" }, effect: { type: "reload" } };
  if (name === "h") return { state: { ...state, screen: "history", rowIndex: 0 }, effect: { type: "open", screen: "history" } };

  if (atHome) {
    const length = ctx.menu.length || MENU_SCREENS.length;
    if (name === "up" || name === "k") return { state: { ...state, menuIndex: nextIndex(state.menuIndex, -1, length) }, effect: null };
    if (name === "down" || name === "j") return { state: { ...state, menuIndex: nextIndex(state.menuIndex, 1, length) }, effect: null };
    if (name === "return" || name === "enter") {
      const target = MENU_SCREENS[state.menuIndex];
      if (target === "quit" || target === undefined) return { state, effect: { type: "quit" } };
      return { state: { ...state, screen: target, rowIndex: 0, note: "" }, effect: { type: "open", screen: target } };
    }
    return { state, effect: null };
  }

  // Inside a screen.
  if (name === "escape" || name === "left") {
    if (name === "left" && state.rowIndex < 0) return { state, effect: null };
    if (name === "left") {
      const row = ctx.rows[state.rowIndex];
      if (row && row.kind === "cycle") return { state, effect: { type: "cycle", id: row.id, delta: -1 } };
    }
    return { state: { ...state, screen: "home", rowIndex: 0, note: "" }, effect: { type: "back" } };
  }
  const rows = ctx.rows;
  if (name === "up" || name === "k") return { state: { ...state, rowIndex: nextIndex(state.rowIndex, -1, Math.max(rows.length, 1)) }, effect: null };
  if (name === "down" || name === "j") return { state: { ...state, rowIndex: nextIndex(state.rowIndex, 1, Math.max(rows.length, 1)) }, effect: null };
  if (name === "right") {
    const row = rows[state.rowIndex];
    if (row && row.kind === "cycle") return { state, effect: { type: "cycle", id: row.id, delta: 1 } };
    return { state, effect: null };
  }
  if (name === "space") {
    const row = rows[state.rowIndex];
    if (row && (row.kind === "toggle" || row.kind === "cycle")) {
      return { state, effect: row.kind === "toggle" ? { type: "toggle", id: row.id } : { type: "cycle", id: row.id, delta: 1 } };
    }
    return { state, effect: null };
  }
  if (name === "return" || name === "enter") {
    const row = rows[state.rowIndex];
    if (!row) return { state, effect: null };
    if (row.kind === "back") return { state: { ...state, screen: "home", rowIndex: 0 }, effect: { type: "back" } };
    if (row.kind === "edit") return { state, effect: { type: "edit", id: row.id } };
    if (row.kind === "toggle") return { state, effect: { type: "toggle", id: row.id } };
    if (row.kind === "cycle") return { state, effect: { type: "cycle", id: row.id, delta: 1 } };
    return { state, effect: { type: "read", id: row.id } };
  }
  return { state, effect: null };
}
