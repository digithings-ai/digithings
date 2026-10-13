import { expect, test } from "bun:test";
import { INITIAL_UI, type KeyCtx, MENU_SCREENS, nextIndex, reduceKey } from "./keys";

const MENU = ["a", "b", "c", "d", "e", "f", "Quit"];
const ctx: KeyCtx = {
  menu: MENU,
  rows: [
    { id: "stt_model", kind: "edit" },
    { id: "rewrite_enabled", kind: "toggle" },
    { id: "banner_position", kind: "cycle" },
    { id: "back", kind: "back" },
  ],
};

test("nextIndex wraps both ways", () => {
  expect(nextIndex(0, -1, 5)).toBe(4);
  expect(nextIndex(4, 1, 5)).toBe(0);
  expect(nextIndex(0, 1, 0)).toBe(0);
});

test("q quits from anywhere", () => {
  expect(reduceKey(INITIAL_UI, { name: "q" }, ctx).effect).toEqual({ type: "quit" });
});

test("home moves the menu and opens a screen", () => {
  const down = reduceKey(INITIAL_UI, { name: "down" }, ctx);
  expect(down.state.menuIndex).toBe(1);
  const open = reduceKey(INITIAL_UI, { name: "return" }, ctx);
  expect(open.state.screen).toBe("models");
  expect(open.effect).toEqual({ type: "open", screen: "models" });
});

test("the last menu entry is Quit", () => {
  expect(MENU_SCREENS[6]).toBe("quit");
  const state = { ...INITIAL_UI, menuIndex: 6 };
  expect(reduceKey(state, { name: "enter" }, ctx).effect).toEqual({ type: "quit" });
});

test("escape returns to home", () => {
  const inScreen = { ...INITIAL_UI, screen: "models" as const };
  const back = reduceKey(inScreen, { name: "escape" }, ctx);
  expect(back.state.screen).toBe("home");
  expect(back.effect).toEqual({ type: "back" });
});

test("enter acts on the highlighted row by kind", () => {
  const base = { ...INITIAL_UI, screen: "models" as const };
  expect(reduceKey({ ...base, rowIndex: 0 }, { name: "return" }, ctx).effect).toEqual({ type: "edit", id: "stt_model" });
  expect(reduceKey({ ...base, rowIndex: 1 }, { name: "return" }, ctx).effect).toEqual({ type: "toggle", id: "rewrite_enabled" });
  expect(reduceKey({ ...base, rowIndex: 3 }, { name: "return" }, ctx).effect).toEqual({ type: "back" });
});

test("right and space cycle, space toggles", () => {
  const base = { ...INITIAL_UI, screen: "models" as const };
  expect(reduceKey({ ...base, rowIndex: 2 }, { name: "right" }, ctx).effect).toEqual({ type: "cycle", id: "banner_position", delta: 1 });
  expect(reduceKey({ ...base, rowIndex: 1 }, { name: "space" }, ctx).effect).toEqual({ type: "toggle", id: "rewrite_enabled" });
});

test("h opens history, r reloads", () => {
  expect(reduceKey(INITIAL_UI, { name: "h" }, ctx).effect).toEqual({ type: "open", screen: "history" });
  expect(reduceKey(INITIAL_UI, { name: "r" }, ctx).effect).toEqual({ type: "reload" });
});
