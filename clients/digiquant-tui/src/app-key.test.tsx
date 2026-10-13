import { describe, expect, test } from "bun:test";
import { act } from "react";
import { testRender } from "@opentui/react/test-utils";
import { App } from "./app";

/** App-level pins for key handling and view switching.
 *
 * `app.tsx` owns every key branch (desk, path palette, rail width, page move,
 * grid focus/move/resize, escape) and every view switch (brief, portfolio,
 * pipeline, strategies, chat, catalog grid, web slot), but no test imported
 * it: the suite covers the helpers it calls, never the wiring. These tests
 * drive the real `App` through `mockInput` and read the real terminal cells
 * back out of `captureCharFrame()`, so a key that stops reaching its branch
 * or a path that stops mounting its view fails here.
 *
 * The header line `desk: Baseline ▾ <path>` is the view-switch proof: it
 * renders the live `path` state, so it names the mounted view directly. */

async function renderApp() {
  const setup = await testRender(<App />, { width: 100, height: 30 });
  await setup.renderOnce();
  return setup;
}

type Setup = Awaited<ReturnType<typeof renderApp>>;

async function frame(setup: Setup): Promise<string> {
  await setup.renderOnce();
  return text(setup.captureCharFrame());
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
    const setup = await renderApp();
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

  test("d opens the desk list and enter picks the desk", async () => {
    const setup = await renderApp();
    try {
      // The blurb only paints inside the open desk list, never in the header.
      expect(await frame(setup)).not.toContain("The house pipeline desk");
      act(() => {
        setup.mockInput.typeText("d");
      });
      expect(await frame(setup)).toContain("The house pipeline desk");
      act(() => {
        setup.mockInput.pressEnter();
      });
      const picked = await frame(setup);
      expect(picked).not.toContain("The house pipeline desk");
      expect(picked).toContain("desk: Baseline ▾ /brief");
    } finally {
      await teardown(setup);
    }
  }, 30000);

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
    const { setup } = await goTo("settings");
    try {
      const unfocused = await frame(setup);
      expect(unfocused).toContain("desk: Baseline ▾ /settings");
      expect(unfocused).not.toContain("tab block");
      act(() => {
        setup.mockInput.pressTab();
      });
      expect(await frame(setup)).toContain("tab block");
      act(() => {
        setup.mockInput.pressArrow("right");
      });
      expect(await frame(setup)).toContain("moved");
      act(() => {
        setup.mockInput.pressArrow("right", { shift: true });
      });
      expect(await frame(setup)).toContain("resized");
      act(() => {
        setup.mockInput.pressEscape();
      });
      const cleared = await frame(setup);
      expect(cleared).not.toContain("tab block");
      expect(cleared).not.toContain("moved");
      expect(cleared).not.toContain("resized");
    } finally {
      await teardown(setup);
    }
  }, 30000);
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
