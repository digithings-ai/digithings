import {
  DEFAULT_PREFS,
  activateSetting,
  applyChoice,
  choiceOptions,
  insertMention,
  mentionRows,
  nextIndex,
  paletteRows,
  paneRows,
  pickPalette,
  selectProvider,
  submitDraft,
  type ChatPrefs,
  type CommandResult,
  type Pane,
} from "./palette";

export type Tray = "input" | "attach" | "voice" | "send";

export type UiState = {
  draft: string;
  focus: "thread" | "composer";
  tray: Tray;
  pathing: boolean;
  path: string;
  paletteIndex: number;
  choice: { id: string; index: number } | null;
  pane: Pane | null;
  paneIndex: number;
  prefs: ChatPrefs;
  attachments: string[];
  note: string;
  scroll: number;
  open: string[];
  editing: boolean;
};

export type KeyIn = { name?: string; ctrl?: boolean; sequence?: string };

export type KeyCtx = {
  busy: boolean;
  canSend: boolean;
  sessionCount: number;
  canCopy: boolean;
  canRetry: boolean;
  lastUserText: string;
  lastFoldable: string | null;
  toolNames: readonly string[];
};

export type KeyEffect =
  | { type: "quit" }
  | { type: "submit"; text: string; note: string }
  | { type: "abort" }
  | { type: "new-session" }
  | { type: "move-session"; delta: number }
  | { type: "redo" }
  | { type: "copy" };

export type KeyResult = { state: UiState; effect: KeyEffect | null };

export const INITIAL_UI: UiState = {
  draft: "",
  focus: "composer",
  tray: "input",
  pathing: false,
  path: "",
  paletteIndex: 0,
  choice: null,
  pane: null,
  paneIndex: 0,
  prefs: DEFAULT_PREFS,
  attachments: [],
  note: "",
  scroll: 0,
  open: [],
  editing: false,
};

const TRAYS: readonly Tray[] = ["input", "attach", "voice", "send"];

function apply(state: UiState, result: CommandResult): KeyResult {
  if (result.type === "draft") {
    return {
      state: { ...state, draft: result.draft, note: result.note, paletteIndex: 0, focus: "composer", pane: null },
      effect: null,
    };
  }
  if (result.type === "prefs") {
    return {
      state: { ...state, prefs: result.prefs, note: result.note, draft: "", choice: null, paletteIndex: 0 },
      effect: null,
    };
  }
  if (result.type === "choices") {
    return {
      state: { ...state, pane: null, choice: { id: result.id, index: 0 }, note: result.note },
      effect: null,
    };
  }
  if (result.type === "pane") {
    return {
      state: { ...state, pane: result.pane, paneIndex: 0, draft: "", choice: null, focus: "thread", note: result.note },
      effect: null,
    };
  }
  if (result.type === "new-session") {
    return {
      state: { ...state, draft: "", choice: null, pane: null, note: result.note, focus: "thread" },
      effect: { type: "new-session" },
    };
  }
  if (result.type === "sessions") {
    return { state: { ...state, draft: "", choice: null, pane: null, focus: "thread", note: result.note }, effect: null };
  }
  if (result.type === "copy") {
    return { state: { ...state, draft: "", pane: null, note: "copied" }, effect: { type: "copy" } };
  }
  if (result.type === "export") {
    return { state: { ...state, pane: "export", paneIndex: 0, draft: "", choice: null, focus: "thread" }, effect: null };
  }
  if (result.type === "redo") {
    return { state: { ...state, draft: "", pane: null, note: result.note }, effect: { type: "redo" } };
  }
  if (result.type === "send") {
    return {
      state: { ...state, draft: "", editing: false, pane: null, note: result.note, paletteIndex: 0, scroll: 0 },
      effect: { type: "submit", text: result.text, note: result.note },
    };
  }
  if (result.type === "block") return { state: { ...state, note: result.note }, effect: null };
  return { state: { ...state, pane: null, note: result.note }, effect: null };
}

function pickChoice(state: UiState): KeyResult {
  const choice = state.choice;
  if (!choice) return { state, effect: null };
  const id = choice.id || paletteCommandId(state);
  const options = choiceOptions(id, state.prefs);
  const selected = options[choice.index];
  if (!selected) return { state: { ...state, choice: null }, effect: null };
  const next = apply(state, applyChoice(id, selected.value, state.prefs));
  return { state: { ...next.state, choice: null, draft: "" }, effect: next.effect };
}

function paletteCommandId(state: UiState): string {
  return state.choice?.id ?? "";
}

function finishCommand(state: UiState, result: CommandResult, ctx: KeyCtx): KeyResult {
  if (result.type === "copy" && !ctx.canCopy) return { state: { ...state, note: "nothing to copy", draft: "" }, effect: null };
  if (result.type === "redo" && !ctx.lastUserText) {
    if (ctx.canRetry) return { state: { ...state, draft: "", pane: null }, effect: { type: "redo" } };
    return { state: { ...state, note: "nothing to redo", draft: "" }, effect: null };
  }
  if (result.type === "redo" && ctx.busy) return { state, effect: null };
  return apply(state, result);
}

function onPaletteEnter(state: UiState, ctx: KeyCtx): KeyResult {
  const rows = paletteRows(state.draft, state.prefs);
  const row = rows[state.paletteIndex];
  if (!row) return finishCommand(state, submitDraft(state.draft, state.prefs), ctx);
  return finishCommand(state, pickPalette(row.id, state.prefs), ctx);
}

function onMentionEnter(state: UiState, ctx: KeyCtx): KeyResult | null {
  if (!state.draft.match(/(^|\s)@[^\s]*$/)) return null;
  const rows = mentionRows(state.draft, ctx.toolNames);
  if (rows.length === 0) return null;
  const row = rows[Math.min(state.paletteIndex, rows.length - 1)];
  if (!row) return null;
  return { state: { ...state, draft: insertMention(state.draft, row.id), paletteIndex: 0, note: "" }, effect: null };
}

function cycleTray(tray: Tray, delta: number): Tray {
  const index = TRAYS.indexOf(tray);
  return TRAYS[nextIndex(index < 0 ? 0 : index, delta, TRAYS.length)] ?? "input";
}

function typeChar(state: UiState, ch: string): UiState {
  return { ...state, draft: state.draft + ch, tray: "input", paletteIndex: 0, editing: state.editing };
}

export function reduceKey(state: UiState, key: KeyIn, ctx: KeyCtx): KeyResult {
  if (key.ctrl) return { state, effect: null };
  const name = key.name ?? "";

  if (state.pane) {
    const rows = paneRows(state.pane, state.prefs);
    if (name === "escape") return { state: { ...state, pane: null, paneIndex: 0 }, effect: null };
    if (name === "up" || name === "k") {
      return { state: { ...state, paneIndex: nextIndex(state.paneIndex, -1, Math.max(rows.length, 1)) }, effect: null };
    }
    if (name === "down" || name === "j") {
      return { state: { ...state, paneIndex: nextIndex(state.paneIndex, 1, Math.max(rows.length, 1)) }, effect: null };
    }
    if (name === "return" || name === "enter") {
      const row = rows[state.paneIndex];
      if (!row) return { state, effect: null };
      if (state.pane === "settings") return finishCommand(state, activateSetting(row.id, state.prefs), ctx);
      if (state.pane === "provider" && row.id !== "keys") {
        return finishCommand(state, selectProvider(row.id, state.prefs), ctx);
      }
      if (state.pane === "more" && row.id === "export") {
        return { state: { ...state, pane: "export", paneIndex: 0 }, effect: null };
      }
      if (state.pane === "help") return finishCommand(state, pickPalette(row.id, state.prefs), ctx);
      if (row.id === "new") return { state: { ...state, note: "OAuth needs a browser" }, effect: null };
      if (row.id === "keys") {
        return { state: { ...state, note: "keys are not entered — this route accepts text only" }, effect: null };
      }
    }
    return { state, effect: null };
  }

  if (state.choice) {
    const options = choiceOptions(state.choice.id, state.prefs);
    if (name === "escape") return { state: { ...state, choice: null }, effect: null };
    if (name === "up" || name === "k") {
      return { state: { ...state, choice: { ...state.choice, index: nextIndex(state.choice.index, -1, options.length) } }, effect: null };
    }
    if (name === "down" || name === "j") {
      return { state: { ...state, choice: { ...state.choice, index: nextIndex(state.choice.index, 1, options.length) } }, effect: null };
    }
    if (name === "return" || name === "enter") return pickChoice(state);
    return { state, effect: null };
  }

  if (state.focus === "composer" && state.pathing) {
    if (name === "escape") return { state: { ...state, pathing: false, path: "", tray: "input" }, effect: null };
    if (name === "return" || name === "enter") {
      const path = state.path.trim();
      const nameOnly = path.split(/[\\/]/).pop() ?? path;
      const attachments = path ? [...state.attachments, nameOnly] : state.attachments;
      return {
        state: { ...state, pathing: false, path: "", attachments, tray: "input", note: path ? "" : state.note },
        effect: null,
      };
    }
    if (name === "backspace") return { state: { ...state, path: state.path.slice(0, -1) }, effect: null };
    const ch = key.sequence && key.sequence.length === 1 ? key.sequence : name.length === 1 ? name : "";
    if (ch.length === 1 && ch >= " ") return { state: { ...state, path: state.path + ch }, effect: null };
    return { state, effect: null };
  }

  if (state.focus === "composer") {
    const rows = paletteRows(state.draft, state.prefs);
    const mentions = mentionRows(state.draft, ctx.toolNames);
    const list = rows.length > 0 ? rows : mentions;
    if ((name === "up" || name === "down") && list.length > 0) {
      const delta = name === "up" ? -1 : 1;
      return { state: { ...state, paletteIndex: nextIndex(state.paletteIndex, delta, list.length) }, effect: null };
    }
    if (name === "escape") {
      if (rows.length > 0 || mentions.length > 0 || state.draft.startsWith("/")) {
        return { state: { ...state, draft: "", paletteIndex: 0, note: "" }, effect: null };
      }
      return { state: { ...state, focus: "thread", tray: "input", editing: false }, effect: null };
    }
    if (name === "tab") return { state: { ...state, tray: cycleTray(state.tray, 1) }, effect: null };
    if (name === "return" || name === "enter") {
      if (state.tray === "attach") return { state: { ...state, pathing: true, path: "" }, effect: null };
      if (state.tray === "voice") {
        return { state: { ...state, tray: "input", note: "voice input is not available in the terminal" }, effect: null };
      }
      if (ctx.busy) return { state, effect: { type: "abort" } };
      if (!ctx.canSend) return { state: { ...state, note: "can't send" }, effect: null };
      if (rows.length > 0) return onPaletteEnter(state, ctx);
      const mention = onMentionEnter(state, ctx);
      if (mention) return mention;
      const sent = finishCommand(state, submitDraft(state.draft, state.prefs), ctx);
      if (state.attachments.length > 0 && sent.effect?.type === "submit") {
        return {
          state: { ...sent.state, attachments: [], note: "attachment not sent — this route accepts text only" },
          effect: sent.effect,
        };
      }
      return sent;
    }
    if (name === "backspace") {
      if (!state.draft && state.attachments.length > 0) {
        return { state: { ...state, attachments: state.attachments.slice(0, -1) }, effect: null };
      }
      return { state: { ...state, draft: state.draft.slice(0, -1), paletteIndex: 0 }, effect: null };
    }
    if (name === "up" && rows.length === 0) return { state: { ...state, focus: "thread", tray: "input" }, effect: null };
    const ch = key.sequence && key.sequence.length === 1 ? key.sequence : name.length === 1 ? name : "";
    if (ch.length === 1 && ch >= " ") return { state: typeChar(state, ch), effect: null };
    return { state, effect: null };
  }

  if (name === "q") return { state, effect: { type: "quit" } };
  if (name === "i" || name === "return" || name === "enter") {
    return { state: { ...state, focus: "composer", tray: "input" }, effect: null };
  }
  if (name === "/" || key.sequence === "/") return { state: { ...state, focus: "composer", draft: "/", paletteIndex: 0 }, effect: null };
  if (name === "n") return { state, effect: { type: "new-session" } };
  if (name === "a") return { state: { ...state, focus: "composer", pathing: true, path: "" }, effect: null };
  if (name === "down" || name === "j") return { state, effect: { type: "move-session", delta: 1 } };
  if (name === "up" || name === "k") return { state, effect: { type: "move-session", delta: -1 } };
  if (name === "c") {
    if (!ctx.canCopy) return { state: { ...state, note: "nothing to copy" }, effect: null };
    return { state: { ...state, note: "copied" }, effect: { type: "copy" } };
  }
  if (name === "r") {
    if (ctx.busy) return { state, effect: null };
    if (!ctx.lastUserText && !ctx.canRetry) return { state: { ...state, note: "nothing to redo" }, effect: null };
    return { state: { ...state, scroll: 0 }, effect: { type: "redo" } };
  }
  if (name === "m") return { state: { ...state, pane: "more", paneIndex: 0 }, effect: null };
  if (name === "e") {
    if (!ctx.lastUserText) return { state: { ...state, note: "nothing to edit" }, effect: null };
    return {
      state: {
        ...state,
        draft: ctx.lastUserText,
        focus: "composer",
        editing: true,
        note: "editing — this route appends",
      },
      effect: null,
    };
  }
  if (name === "b" || name === "end") return { state: { ...state, scroll: 0 }, effect: null };
  if (name === "pageup") return { state: { ...state, scroll: state.scroll + 8 }, effect: null };
  if (name === "pagedown") return { state: { ...state, scroll: Math.max(0, state.scroll - 8) }, effect: null };
  if (name === "o" && ctx.lastFoldable) {
    const id = ctx.lastFoldable;
    const open = state.open.includes(id) ? state.open.filter((item) => item !== id) : [...state.open, id];
    return { state: { ...state, open }, effect: null };
  }
  if (name === "?" || key.sequence === "?") return { state: { ...state, pane: "help", paneIndex: 0 }, effect: null };
  if (name === "s") return { state: { ...state, pane: "settings", paneIndex: 0 }, effect: null };
  return { state, effect: null };
}
