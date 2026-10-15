import { describe, expect, test } from "bun:test";
import { act } from "react";
import { testRender } from "@opentui/react/test-utils";
import { App } from "./app";
import { ACCENT } from "./theme";

/** App-level pins for key handling and view switching.
 *
 * `app.tsx` owns every key branch (desk, path palette, rail width, page move,
 * grid focus/move/resize, escape) and every view switch (brief, portfolio,
 * pipeline, strategies, chat, catalog grid, web slot), but no test imported
 * it: the suite covers the helpers it calls, never the wiring. These tests
 * drive the real `App` through `mockInput`/`mockMouse` and read the real
 * terminal cells back out of `captureCharFrame()`/`captureSpans()`, so a key
 * that stops reaching its branch or a path that stops mounting its view
 * fails here.
 *
 * The header line `desk: Baseline ▾ <path>` is the view-switch proof: it
 * renders the live `path` state, so it names the mounted view directly.
 *
 * Three input-pipeline facts shape these tests (each measured, not assumed):
 * - A lone ESC byte is held by the input parser (ambiguous prefix), so
 *   `pressEscape` in the default mode never resolves. `kittyKeyboard: true`
 *   encodes it unambiguously and delivers `escape` at once.
 * - `\r` parses as `return`, never `enter`, in both modes, while `app.tsx`
 *   matches `name === "enter"`. The enter key is therefore undeliverable
 *   through this pipeline, so the desk pick is pinned through the mouse
 *   (`onPick`) instead, which runs the same `chooseDesk`.
 * - The footer (`q quit`, `tab block`, `moved`, notes) never paints: a
 *   1-row box carrying a top border spends its row on the rule. Grid focus
 *   is pinned through `captureSpans()` (the focused title paints ACCENT)
 *   and move/resize through the title's line position and text, which the
 *   animated mark cannot shift. */

async function renderApp(kitty = false) {
  const setup = await testRender(<App />, { width: 100, height: 30, kittyKeyboard: kitty });
  await setup.renderOnce();
  return setup;
}

type Setup = Awaited<ReturnType<typeof renderApp>>;

async function frame(setup: Setup): Promise<string> {
  await setup.renderOnce();
  return text(setup.captureCharFrame());
}

async function rawFrame(setup: Setup): Promise<string> {
  await setup.renderOnce();
  return setup.captureCharFrame();
}

/** The header wraps the path onto padded columns, so collapse whitespace
 * before matching header text. Rail rows never carry "desk:", so a
 * `desk: Baseline <path>` match still names the mounted view. */
function text(frame: string): string {
  return frame.replace(/\s+/g, " ");
}

async function teardown(setup: Setup): Promise<void> {
  act(() => setup.renderer.destroy());
}

/** Span texts painted in the theme ACCENT. The focused grid title and border
 * are the only ACCENT on a catalog page besides the rail highlight, so the
 * rail row is the control proving the walker fires. */
function accentTexts(spans: unknown): string[] {
  const hex = ACCENT.replace("#", "");
  const rgb = [parseInt(hex.slice(0, 2), 16), parseInt(hex.slice(2, 4), 16), parseInt(hex.slice(4, 6), 16)];
  const out: string[] = [];
  const walk = (node: unknown): void => {
    if (Array.isArray(node)) {
      for (const item of node) walk(item);
      return;
    }
    if (node && typeof node === "object") {
      const rec = node as Record<string, unknown>;
      const fg = rec.fg as { buffer?: Record<number, number> } | undefined;
      if (typeof rec.text === "string" && fg && typeof fg === "object" && fg.buffer) {
        const b = fg.buffer;
        if (b[0] === rgb[0] && b[1] === rgb[1] && b[2] === rgb[2]) out.push(rec.text as string);
      }
      for (const value of Object.values(rec)) walk(value);
    }
  };
  walk(spans);
  return out;
}

/** Raw-frame line holding the focused block's top border. A move changes its
 * position; a resize changes its text; the animated mark can do neither. */
function titleLineIndex(raw: string): number {
  return raw.split("\n").findIndex((line) => line.includes("Settings · prefs") && line.includes("┌"));
}

function titleLineText(raw: string): string {
  return (raw.split("\n").find((line) => line.includes("Settings · prefs") && line.includes("┌")) ?? "").trim();
}

/** Drive the path palette (`/` … type … enter) to the queried page and read
 * the frame. The first hit is the queried page itself for every query used
 * below, and the header names it, so a wrong pick fails on the header. */
async function goTo(query: string): Promise<{ setup: Setup; frame: string }> {
  const setup = await renderApp();
  act(() => {
    setup.mockInput.typeText("/");
  });
  await setup.renderOnce();
  act(() => {
    setup.mockInput.typeText(query);
  });
  await setup.renderOnce();
  act(() => {
    setup.mockInput.pressEnter();
  });
  return { setup, frame: await frame(setup) };
}

describe("app key handling", () => {
  test("slash opens the path palette and escape closes it", async () => {
    const setup = await renderApp(true);
    try {
      expect(await frame(setup)).toContain("desk: Baseline ▾ /brief");
      act(() => {
        setup.mockInput.typeText("/");
      });
      expect(await frame(setup)).toContain("go to");
      act(() => {
        setup.mockInput.pressEscape();
      });
      const closed = await frame(setup);
      expect(closed).toContain("desk: Baseline ▾ /brief");
      expect(closed).not.toContain("go to");
    } finally {
      await teardown(setup);
    }
  }, 30000);

  test("d opens the desk list, d toggles it, escape closes it, a click picks", async () => {
    const setup = await renderApp(true);
    try {
      // The blurb only paints inside the open desk list, never in the header.
      expect(await frame(setup)).not.toContain("The house pipeline desk");
      act(() => {
        setup.mockInput.typeText("d");
      });
      expect(await frame(setup)).toContain("The house pipeline desk");
      act(() => {
        setup.mockInput.typeText("d");
      });
      expect(await frame(setup)).not.toContain("The house pipeline desk");
      act(() => {
        setup.mockInput.typeText("d");
      });
      expect(await frame(setup)).toContain("The house pipeline desk");
      act(() => {
        setup.mockInput.pressEscape();
      });
      expect(await frame(setup)).not.toContain("The house pipeline desk");
      act(() => {
        setup.mockInput.typeText("d");
      });
      expect(await frame(setup)).toContain("The house pipeline desk");
      // A click on the divider row above the list is a no-op control: it
      // proves the close below comes from the pick row, not any click.
      await act(async () => {
        await setup.mockMouse.click(50, 2);
      });
      expect(await frame(setup)).toContain("The house pipeline desk");
      await act(async () => {
        await setup.mockMouse.click(50, 3);
      });
      const picked = await frame(setup);
      expect(picked).not.toContain("The house pipeline desk");
      expect(picked).toContain("desk: Baseline ▾ /brief");
    } finally {
      await teardown(setup);
    }
  }, 60000);

  test("brackets narrow and widen the rail", async () => {
    const setup = await renderApp();
    try {
      // The full attribution path fits the default 36-column rail only.
      expect(await frame(setup)).toContain("/portfolio/attribution");
      act(() => {
        setup.mockInput.typeText("[");
      });
      expect(await frame(setup)).not.toContain("/portfolio/attribution");
      act(() => {
        setup.mockInput.typeText("]");
      });
      expect(await frame(setup)).toContain("/portfolio/attribution");
    } finally {
      await teardown(setup);
    }
  }, 30000);

  test("down and up move between rail pages", async () => {
    const setup = await renderApp();
    try {
      expect(await frame(setup)).toContain("desk: Baseline ▾ /brief");
      act(() => {
        setup.mockInput.pressArrow("down");
      });
      expect(await frame(setup)).toContain("desk: Baseline ▾ /portfolio");
      act(() => {
        setup.mockInput.pressArrow("up");
      });
      expect(await frame(setup)).toContain("desk: Baseline ▾ /brief");
    } finally {
      await teardown(setup);
    }
  }, 30000);

  test("tab focuses a grid block, arrows move it, shift-arrows resize it, escape clears it", async () => {
    // Arrow navigation, never the palette: a mounted palette input keeps
    // focus after it unmounts and swallows later tabs in the focus manager.
    const setup = await renderApp(true);
    await setup.renderOnce();
    try {
      for (let i = 0; i < 14; i++) {
        act(() => {
          setup.mockInput.pressArrow("down");
        });
        await setup.renderOnce();
      }
      expect(await frame(setup)).toContain("desk: Baseline ▾ /settings");
      const railAccent = accentTexts(setup.captureSpans()).join("");
      // Control: the walker fires (rail highlight), but no block title does.
      expect(railAccent).toContain("▾ /settings");
      expect(accentTexts(setup.captureSpans()).join("")).not.toContain("Settings · prefs");
      act(() => {
        setup.mockInput.pressTab();
      });
      await setup.flush();
      expect(accentTexts(setup.captureSpans()).join("")).toContain("Settings · prefs");
      // Control: an unbound key moves nothing, so the position reads below
      // are live measurements, not drift.
      const settled = await rawFrame(setup);
      act(() => {
        setup.mockInput.typeText("z");
      });
      expect(titleLineIndex(await rawFrame(setup))).toBe(titleLineIndex(settled));
      const resizedBefore = titleLineText(await rawFrame(setup));
      act(() => {
        setup.mockInput.pressArrow("left", { shift: true });
      });
      await setup.flush();
      // Narrowing the block rewrites its title padding.
      expect(titleLineText(await rawFrame(setup))).not.toBe(resizedBefore);
      const movedBefore = titleLineIndex(await rawFrame(setup));
      act(() => {
        setup.mockInput.pressArrow("down");
      });
      await setup.flush();
      expect(titleLineIndex(await rawFrame(setup))).not.toBe(movedBefore);
      act(() => {
        setup.mockInput.pressEscape();
      });
      await setup.flush();
      const cleared = accentTexts(setup.captureSpans()).join("");
      expect(cleared).not.toContain("Settings · prefs");
      expect(cleared).toContain("▾ /settings");
    } finally {
      await teardown(setup);
    }
  }, 60000);
});

describe("app view switching", () => {
  test("the brief view mounts for /brief", async () => {
    const setup = await renderApp();
    try {
      const initial = await frame(setup);
      expect(initial).toContain("desk: Baseline ▾ /brief");
      expect(initial).toContain("Brief");
    } finally {
      await teardown(setup);
    }
  }, 30000);

  test("the portfolio view mounts for /portfolio", async () => {
    const { setup, frame: initial } = await goTo("portfolio");
    try {
      expect(initial).toContain("desk: Baseline ▾ /portfolio");
      expect(initial).toContain("Exposure");
    } finally {
      await teardown(setup);
    }
  }, 30000);

  test("the pipeline view mounts for /pipeline", async () => {
    const { setup, frame: initial } = await goTo("pipeline");
    try {
      expect(initial).toContain("desk: Baseline ▾ /pipeline");
      expect(initial).toContain("Artifact");
    } finally {
      await teardown(setup);
    }
  }, 30000);

  test("the strategies view mounts for /strategies", async () => {
    const { setup, frame: initial } = await goTo("strategies");
    try {
      expect(initial).toContain("desk: Baseline ▾ /strategies");
      expect(initial).toContain("Strategies");
    } finally {
      await teardown(setup);
    }
  }, 30000);

  test("the chat view mounts for /tools/chat", async () => {
    const { setup, frame: initial } = await goTo("tools/chat");
    try {
      expect(initial).toContain("desk: Baseline ▾ /tools/chat");
      expect(initial).toContain("loading…");
      expect(initial).not.toContain("This page is not drawn on the terminal.");
    } finally {
      await teardown(setup);
    }
  }, 30000);

  test("the catalog grid mounts for /settings", async () => {
    const { setup, frame: initial } = await goTo("settings");
    try {
      expect(initial).toContain("desk: Baseline ▾ /settings");
      expect(initial).toContain("Settings");
    } finally {
      await teardown(setup);
    }
  }, 30000);

  test("a web slot stays undrawn for /tools/terminal", async () => {
    const { setup, frame: initial } = await goTo("tools/terminal");
    try {
      expect(initial).toContain("desk: Baseline ▾ /tools/terminal");
      expect(initial).toContain("This page is not drawn on the terminal.");
    } finally {
      await teardown(setup);
    }
  }, 30000);
});
