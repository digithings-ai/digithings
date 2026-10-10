/**
 * Headless capture for the digivoice-tui visual gate.
 *
 * Renders the real <App/> with opentui's test renderer at a fixed cell grid,
 * optionally navigates to a screen, and prints the captured frame as JSON
 * (cols, rows, and per-line spans with fg/bg). A companion renderer turns that
 * JSON into a PNG. Screenshots are throwaway review artifacts, not repo files.
 *
 * Usage: bun scripts/shoot.tsx <cols> <rows> <screen> [out.json]
 */
import { createTestRenderer } from "@opentui/core/testing";
import { createRoot } from "@opentui/react";
import { App } from "../src/app";

const [, , colsArg, rowsArg, screenArg, outArg] = process.argv;
const cols = Number(colsArg) || 80;
const rows = Number(rowsArg) || 24;
const screen = screenArg || "home";

// menuIndex starts at 0 (Models). Enter opens MENU_SCREENS[menuIndex], so a
// screen at menu row N needs N DOWNs then RETURN.
const NAV: Record<string, string[]> = {
  home: [],
  models: ["RETURN"],
  features: ["ARROW_DOWN", "RETURN"],
  hotkeys: ["ARROW_DOWN", "ARROW_DOWN", "RETURN"],
  hardware: ["ARROW_DOWN", "ARROW_DOWN", "ARROW_DOWN", "RETURN"],
  review: ["ARROW_DOWN", "ARROW_DOWN", "ARROW_DOWN", "ARROW_DOWN", "RETURN"],
  doctor: ["ARROW_DOWN", "ARROW_DOWN", "ARROW_DOWN", "ARROW_DOWN", "ARROW_DOWN", "RETURN"],
  history: ["h"],
};

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

const setup = await createTestRenderer({ width: cols, height: rows });
const root = createRoot(setup.renderer);
root.render(<App />);

// Let the digivoice CLI reads settle, then navigate, then capture.
await setup.flush();
await sleep(1500);
const keys = NAV[screen] ?? [];
if (keys.length) await setup.mockInput.pressKeys(keys as never, 40);
await setup.flush();
await sleep(500);

const frame = setup.captureSpans();
const json = JSON.stringify({
  cols: frame.cols,
  rows: frame.rows,
  lines: frame.lines.map((line) =>
    line.spans.map((s) => ({ text: s.text, fg: s.fg.toInts(), bg: s.bg.toInts(), attributes: s.attributes })),
  ),
});

if (outArg) await Bun.write(outArg, json);
else console.log(json);

setup.renderer.destroy();
process.exit(0);
