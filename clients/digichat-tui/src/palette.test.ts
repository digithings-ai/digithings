import { expect, test } from "bun:test";
import { exportMarkdown, historySkeleton, sessionTitle, spinnerFrame } from "./chrome";
import { INITIAL_UI, reduceKey } from "./keys";
import { DEFAULT_PREFS, commandIds, paletteRows, submitDraft } from "./palette";

const ctx = {
  busy: false,
  canSend: true,
  sessionCount: 0,
  canCopy: false,
  canRetry: false,
  lastUserText: "",
  lastFoldable: null,
  toolNames: [] as string[],
};

test("the slash palette lists the web configure commands and featured languages", () => {
  const rows = paletteRows("/", DEFAULT_PREFS);
  const labels = rows.map((row) => row.label);
  for (const label of ["/settings", "/websearch", "/provider", "/new", "/export", "/english"]) {
    expect(labels).toContain(label);
  }
  expect(commandIds()).toContain("mcp");
  expect(paletteRows("/dig", DEFAULT_PREFS).map((row) => row.id)).toEqual(["digisearch", "digivault"]);
  expect(paletteRows("/digisearch ", DEFAULT_PREFS)).toEqual([]);
});

test("an empty tool command toggles and a query is sent as text", () => {
  const toggled = submitDraft("/websearch", DEFAULT_PREFS);
  expect(toggled.type).toBe("prefs");
  if (toggled.type === "prefs") expect(toggled.prefs.webSearch).toBe(true);
  const sent = submitDraft("/digisearch the book", DEFAULT_PREFS);
  expect(sent).toMatchObject({ type: "send", text: "the book" });
  expect(submitDraft("/nope", DEFAULT_PREFS)).toMatchObject({ type: "block", note: "unknown command" });
  expect(submitDraft("/charts", DEFAULT_PREFS)).toMatchObject({
    type: "note",
    note: expect.stringContaining("open in web"),
  });
});

test("enter on / opens a command, and a plain line submits", () => {
  const opened = reduceKey(INITIAL_UI, { sequence: "/" }, ctx);
  expect(opened.state.draft).toBe("/");
  expect(paletteRows(opened.state.draft, opened.state.prefs).length).toBeGreaterThan(10);
  const settings = reduceKey({ ...opened.state, paletteIndex: paletteRows("/", DEFAULT_PREFS).findIndex((row) => row.id === "settings") }, { name: "return" }, ctx);
  expect(settings.state.pane).toBe("settings");
  const typed = reduceKey(INITIAL_UI, { sequence: "h" }, ctx);
  const more = reduceKey(typed.state, { sequence: "i" }, ctx);
  const sent = reduceKey(more.state, { name: "return" }, ctx);
  expect(sent.effect).toEqual({ type: "submit", text: "hi", note: "", attachments: [] });
});

test("voice stays on the tray and a failed read can retry", () => {
  const voiced = reduceKey({ ...INITIAL_UI, tray: "voice" }, { name: "return" }, ctx);
  expect(voiced.state.note).toBe("voice input is not available in the terminal");
  const retried = reduceKey({ ...INITIAL_UI, focus: "thread" }, { name: "r" }, { ...ctx, canRetry: true });
  expect(retried.effect).toEqual({ type: "redo" });
});

test("session titles, the skeleton, and export stay honest", () => {
  expect(sessionTitle("—")).toBe("new chat");
  expect(sessionTitle("book")).toBe("book");
  expect(historySkeleton(40).every((line) => line.text.includes("░"))).toBe(true);
  expect(historySkeleton(40).some((line) => line.text.includes("hello"))).toBe(false);
  expect(spinnerFrame(0)).toBe("⠋");
  expect(spinnerFrame(1)).not.toBe(spinnerFrame(0));
  expect(
    exportMarkdown([
      { id: "u", role: "user", text: "what is flat", tool: null, reasoning: "", at: "" },
      { id: "a", role: "assistant", text: "the book is flat", tool: null, reasoning: "", at: "" },
      { id: "t", role: "assistant", text: "book", tool: { name: "book", status: "", detail: "" }, reasoning: "", at: "" },
    ]),
  ).toBe("## You\n\nwhat is flat\n\n## digichat\n\nthe book is flat");
});
