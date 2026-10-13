import { afterEach, expect, test } from "bun:test";
import { testRender } from "@opentui/react/test-utils";
import type { TestRendererSetup } from "@opentui/core/testing";
import { exportMarkdown } from "./chrome";
import { App } from "./app";
import { INITIAL_UI, reduceKey } from "./keys";
import { DEFAULT_PREFS, paneRows, type Pane } from "./palette";
import { CREDIT, PLACEHOLDER, UNREACHABLE } from "./read";

process.env.DIGI_REDUCED_MOTION = "1";

const PANES: readonly Pane[] = ["settings", "models", "provider", "mcp", "tools", "help", "more"];

const cleanups: TestRendererSetup[] = [];
afterEach(() => {
  for (const setup of cleanups.splice(0)) setup.renderer.destroy();
});

function offlineFetch(): typeof fetch {
  return (() => Promise.reject(new Error("offline for test"))) as typeof fetch;
}

async function settle(setup: TestRendererSetup, ms = 300): Promise<string> {
  await new Promise((resolve) => setTimeout(resolve, ms));
  await setup.flush();
  return setup.captureCharFrame();
}

const keyCtx = {
  busy: false,
  canSend: true,
  sessionCount: 1,
  canCopy: false,
  canRetry: false,
  lastUserText: "",
  lastFoldable: null,
  toolNames: [] as string[],
};

test("App renders the shell, then settles on the unreachable thread view", async () => {
  const realFetch = globalThis.fetch;
  globalThis.fetch = offlineFetch();
  try {
    const setup = await testRender(<App />, { width: 100, height: 30 });
    cleanups.push(setup);
    await setup.flush();
    const first = setup.captureCharFrame();
    expect(first).toContain(PLACEHOLDER);
    expect(first).toContain(CREDIT);
    const settled = await settle(setup);
    expect(settled).toContain(UNREACHABLE);
  } finally {
    globalThis.fetch = realFetch;
  }
});

test("every App pane has at least one view row", () => {
  for (const pane of PANES) {
    const rows = paneRows(pane, DEFAULT_PREFS);
    expect(rows.length).toBeGreaterThan(0);
    for (const row of rows) expect(row.label.trim().length).toBeGreaterThan(0);
  }
  const exported = exportMarkdown([
    { id: "u", role: "user", text: "what is flat", tool: null, reasoning: "", at: "" },
    { id: "a", role: "assistant", text: "the book is flat", tool: null, reasoning: "", at: "" },
  ]);
  expect(exported).toContain("the book is flat");
});

test("the s keybinding opens the settings pane and App renders it", async () => {
  const reduced = reduceKey({ ...INITIAL_UI, focus: "thread" }, { name: "s" }, keyCtx);
  expect(reduced.state.pane).toBe("settings");
  expect(reduced.effect).toBeNull();

  const realFetch = globalThis.fetch;
  globalThis.fetch = offlineFetch();
  try {
    const setup = await testRender(<App />, { width: 100, height: 30 });
    cleanups.push(setup);
    await settle(setup);
    setup.mockInput.pressEscape();
    await settle(setup, 100);
    setup.mockInput.pressKey("s");
    const paneFrame = await settle(setup, 100);
    expect(paneFrame).toContain("language");
  } finally {
    globalThis.fetch = realFetch;
  }
});

test("the more pane leads to the export view", async () => {
  const realFetch = globalThis.fetch;
  globalThis.fetch = offlineFetch();
  try {
    const setup = await testRender(<App />, { width: 100, height: 30 });
    cleanups.push(setup);
    await settle(setup);
    setup.mockInput.pressEscape();
    await settle(setup, 100);
    setup.mockInput.pressKey("m");
    const moreFrame = await settle(setup, 100);
    expect(moreFrame).toContain("export");
    setup.mockInput.pressEnter();
    const exportFrame = await settle(setup, 100);
    expect(exportFrame).toContain("nothing to export");
  } finally {
    globalThis.fetch = realFetch;
  }
});
