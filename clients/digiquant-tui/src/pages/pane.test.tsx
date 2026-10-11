import { describe, expect, test } from "bun:test";
import { act } from "react";
import { testRender } from "@opentui/react/test-utils";
import { PaneFrame, PANE_HINT } from "./pane";
import { INK } from "../theme";

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