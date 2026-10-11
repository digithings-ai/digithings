import { describe, expect, test } from "bun:test";
import { act } from "react";
import { testRender } from "@opentui/react/test-utils";
import { CLOSE_HINT, OPEN_HINT, PaneFrame, PANE_HINT } from "./pane";
import type { PaneBody } from "./shape";
import { DOWN, INK, MUTE, UP } from "../theme";

/** These are render-level assertions on purpose.
 *
 * Every page in this client draws its footer through `PaneFrame`, and a footer
 * that never paints is invisible on all of them at once. A test that asserts on
 * a formatter cannot see that: the formatter was always right and the row was
 * always blank. So these tests render the real component and read the real
 * terminal cells back out of `captureCharFrame()`. */

/** The longest footer the FX desk produces, with the state word last, so a
 *  regression that eats the tail also eats the severity. */
const STALE_FOOTER = "as of 2026-09-17 · 12 trading days old · stale";

/** Height 5 is the floor, not an arbitrary pick: the pane's own border takes
 *  the top and bottom row, the header takes one, and the footer needs one row
 *  for its rule plus one for its words. A 4-row pane cannot fit all three, so
 *  it is excluded here rather than asserted to render something impossible. */
const HEIGHTS = [5, 6, 8, 12, 20, 40];

async function frame(
  width: number,
  height: number,
  status: string,
  focused = false,
): Promise<string> {
  const setup = await testRender(
    <PaneFrame title="TITLEWORD" status={status} focused={focused} lines={["body one", "body two"]} ink={INK} />,
    { width, height },
  );
  await setup.renderOnce();
  const captured = setup.captureCharFrame();
  act(() => setup.renderer.destroy());
  return captured;
}

describe("the pane footer paints its words", () => {
  test("the status string reaches the screen at every size a pane is laid out at", async () => {
    // The defect: `height={1}` on a box that carries a top border spends that
    // one row on the rule, so the text is laid out and then never painted. It
    // held at every size, so the sweep is what stops it coming back at the one
    // size someone happens to re-measure.
    for (const width of [16, 20, 30, 40, 50]) {
      for (const height of HEIGHTS) {
        const captured = await frame(width, height, "FOOTERWORD");
        expect(captured).toContain("FOOTERWORD");
      }
    }
  });

  test("the longest footer the FX desk produces renders whole, state word included", async () => {
    // 46 characters plus the focus hint needs 60 columns of content. Below that
    // the tail is cut, and the tail is the severity.
    const captured = await frame(70, 6, STALE_FOOTER, true);
    expect(captured).toContain(STALE_FOOTER);
    expect(captured).toContain("· stale");
  });

  test("a focused pane still shows the tab hint beside the status", async () => {
    const captured = await frame(70, 6, STALE_FOOTER, true);
    expect(captured).toContain(PANE_HINT);
  });

  test("an unfocused pane shows the status and no hint", async () => {
    const captured = await frame(70, 6, STALE_FOOTER, false);
    expect(captured).toContain(STALE_FOOTER);
    expect(captured).not.toContain(PANE_HINT);
  });

  test("the title and body still paint, so the fix is not a blank pane", async () => {
    // The control. Without it, "make the footer visible" is satisfiable by
    // tearing the whole pane down.
    const captured = await frame(70, 8, STALE_FOOTER, true);
    expect(captured).toContain("TITLEWORD");
    expect(captured).toContain("body one");
    expect(captured).toContain("body two");
    expect(captured).toContain(STALE_FOOTER);
  });

  test("the footer rule is still drawn above the words", async () => {
    // The fix is a height change, not a dropped border. This pins the reason the
    // height had to grow rather than the rule being replaced.
    const rows = (await frame(70, 6, STALE_FOOTER, true)).split("\n");
    const statusRow = rows.findIndex((row) => row.includes(STALE_FOOTER));
    expect(statusRow).toBeGreaterThan(0);
    expect(rows[statusRow - 1]).toMatch(/^│─+│$/);
  });
});
describe("signed figures take the up and down colours", () => {
  /** The hex the terminal stored for the first span whose text holds `needle`. */
  async function inkOf(blocks: PaneBody, needle: string): Promise<string | null> {
    const setup = await testRender(<PaneFrame title="T" status="S" focused={false} blocks={blocks} ink={INK} />, { width: 60, height: 8 });
    await setup.renderOnce();
    const spans = setup.captureSpans().lines.flatMap((line) => line.spans);
    act(() => setup.renderer.destroy());
    const span = spans.find((item) => item.text.includes(needle));
    if (!span) return null;
    const [r, g, b] = [span.fg.r, span.fg.g, span.fg.b].map((c) => Math.round(c * 255).toString(16).padStart(2, "0").toUpperCase());
    return `#${r}${g}${b}`;
  }

  test("a table cell and a stat value colour by sign; zero and unsigned keep their ink", async () => {
    const table: PaneBody = { blocks: [{ kind: "table", columns: [], rows: [["AAA", "+1.25%", "-2.50%", "0.00%"]] }] };
    expect(await inkOf(table, "+1.25%")).toBe(UP.toUpperCase());
    expect(await inkOf(table, "-2.50%")).toBe(DOWN.toUpperCase());
    expect(await inkOf(table, "0.00%")).toBe(INK.toUpperCase());
    const stat: PaneBody = { blocks: [{ kind: "stat", text: "day  -0.40%   invested  80.00%" }] };
    expect(await inkOf(stat, "-0.40%")).toBe(DOWN.toUpperCase());
    expect(await inkOf(stat, "80.00%")).toBe(MUTE.toUpperCase());
  });
});

const WIDE: PaneBody = {
  blocks: [
    {
      kind: "table",
      columns: ["Pair", "Mid", "Bid", "Ask", "Spread", "LASTCOL"],
      rows: Array.from({ length: 12 }, (_, i) => ["USDJPY", "149.123456789", "149.10", "149.14", "0.04", `ROW${i}END`]),
    },
  ],
};

async function paneFrame(width: number, height: number, open: boolean): Promise<string> {
  const setup = await testRender(<PaneFrame title="WIDE" status="as of today" focused open={open} blocks={WIDE} ink={INK} />, { width, height });
  // The first pass lays the body out and measures it; the second paints the face that fits.
  await act(async () => {
    await setup.renderOnce();
  });
  await act(async () => {
    await setup.renderOnce();
  });
  const captured = setup.captureCharFrame();
  act(() => setup.renderer.destroy());
  return captured;
}

describe("a pane opens in place", () => {
  test("closed, it shows the key columns, the rows that fit, and says what it left out", async () => {
    const captured = await paneFrame(40, 10, false);
    expect(captured).toContain(OPEN_HINT);
    expect(captured).toContain("Pair");
    expect(captured).not.toContain("LASTCOL");
    expect(captured).toMatch(/\+\d+ cols/);
    expect(captured).toContain("149.1235");
    expect(captured).not.toContain("149.123456789");
  });

  test("open, it shows every column and the close hint", async () => {
    const captured = await paneFrame(90, 20, true);
    expect(captured).toContain(CLOSE_HINT);
    expect(captured).toContain("LASTCOL");
    expect(captured).toContain("ROW11END");
    expect(captured).not.toMatch(/\+\d+ cols/);
  });
});
