import { describe, expect, test } from "bun:test";
import { act } from "react";
import { testRender } from "@opentui/react/test-utils";
import { PaneFrame } from "./pane";
import { fxBlockLines, fxInk, fxPaneStatus, fxTone } from "./fx";
import { INK, WARN, DANGER } from "../theme";
import type { ReadResult } from "../read";

/** The seam two of our own tests left open.
 *
 * `pane.test.tsx` proves the footer paints a string, but it feeds that string in
 * as a literal. `fx-staleness.test.ts` proves the age words are right, but it
 * never renders anything. So both pass while the defect this issue exists to kill
 * is live: `fxPaneStatus` could return the right words and the row could still
 * drop them, and nothing would notice.
 *
 * That is not hypothetical. `pane.tsx` carried `height={1}` on a box with a top
 * border for its whole life, which spends the row on the rule and paints nothing
 * — while every formatter-level test in this client stayed green. The words have
 * to go through the real component and be read back out of real cells, so these
 * tests call the real formatter and render the real pane. */

/** A read result of the shape `read.ts` produces for a real `/fx/*` route. */
function read(asOf: string | null): ReadResult {
  return { status: "ok", lines: ["run  2026-09-17", "EURUSD  1.0842"], asOf };
}

/** The footer the FX desk would draw for `asOf`, rendered in a real pane.
 *  Returns the captured character frame so callers can assert on painted cells. */
async function painted(asOf: string | null, now: string, width = 70, height = 6): Promise<string> {
  const footer = fxPaneStatus(read(asOf), null, "/fx/summary", now);
  const setup = await testRender(
    <PaneFrame title="FX hub · summary" status={footer} focused={false} lines={["run  2026-09-17"]} ink={INK} />,
    { width, height },
  );
  await setup.renderOnce();
  const captured = setup.captureCharFrame();
  act(() => setup.renderer.destroy());
  return captured;
}

describe("the age words the FX desk computes reach the screen", () => {
  test("a stale read paints its count and its state word", async () => {
    // 2026-09-17 to 2026-10-05 is 12 sessions, so this is the worst case the
    // outage produced and the longest footer the desk can emit.
    const captured = await painted("2026-09-17", "2026-10-05");
    expect(captured).toContain("as of 2026-09-17 · 12 trading days old · stale");
  });

  test("a warn read paints its count and its state word", async () => {
    // The band the trader has to act on: one session is fine, two is behind.
    const captured = await painted("2026-10-01", "2026-10-05");
    expect(captured).toContain("as of 2026-10-01 · 2 trading days old · warn");
  });

  test("a healthy read paints its claim and does not name a state", async () => {
    // The rule from the UI review: an aged pane names its state, an `ok` pane
    // does not, because "current session" is already the claim.
    const captured = await painted("2026-10-05", "2026-10-05");
    expect(captured).toContain("as of 2026-10-05 · current session");
    expect(captured).not.toContain("· ok");
  });

  test("a Friday run read on Sunday still claims the current session", async () => {
    // The weekend rule, at the render level. If age were counted in hours this
    // would read stale, and a permanent Saturday alarm is how a tone gets ignored.
    const captured = await painted("2026-10-02", "2026-10-04");
    expect(captured).toContain("current session");
    expect(captured).not.toContain("stale");
  });

  test("the words survive the narrowest pane the desk lays out", async () => {
    // The tail is the severity. At a narrow width the status is clipped, so this
    // is the size where `· stale` is the first thing to go missing.
    const captured = await painted("2026-09-17", "2026-10-05", 48, 6);
    expect(captured).toContain("12 trading days old");
  });

  test("a stale read is inked differently from a healthy one", async () => {
    // The colour half of the fix, asserted as a fact about the mapping rather
    // than about pixels: `fxInk` is what `FxBlock` hands the pane, so if stale
    // and ok ever share an ink the tone is a lie again.
    const healthy = { status: "ok" as const, lines: ["run  2026-10-05"], asOf: "2026-10-05" };
    const stale = { status: "ok" as const, lines: ["run  2026-09-17"], asOf: "2026-09-17" };
    const healthyInk = fxInk(fxTone(healthy, healthy.lines, { now: "2026-10-05" }));
    const staleInk = fxInk(fxTone(stale, stale.lines, { now: "2026-10-05" }));
    expect(healthyInk).toBe(INK);
    expect(staleInk).toBe(DANGER);
    expect(staleInk).not.toBe(healthyInk);
    expect(WARN).not.toBe(staleInk);
  });
});

describe("the sentence an unprovisioned FX pane shows reaches the screen", () => {
  test("the `fx-sessions` no-state sentence paints, on quiet ink", async () => {
    // Client QA (DIG-2071) chose this copy and then said plainly that it had only
    // judged it from the source string, not from the screen. This closes that
    // limit: the sentence goes through the real block builder and the real pane and
    // is read back out of real cells, so "it reads correctly" is a claim about
    // pixels rather than about a literal in a test file.
    const result: ReadResult = { status: "ok", lines: [], asOf: null };
    const body = fxBlockLines("fx-sessions", result, { sessions: [
      { session: "Asia", state: null, note: null },
      { session: "London", state: null, note: null },
      { session: "New York", state: null, note: null },
    ] });
    const tone = fxTone(result, body);
    expect(tone).toBe("empty");

    const setup = await testRender(
      <PaneFrame
        title="FX · sessions"
        status={fxPaneStatus(result, null, "/fx/sessions", "2026-10-08")}
        focused={false}
        lines={body}
        ink={fxInk(tone)}
      />,
      { width: 60, height: 7 },
    );
    await setup.renderOnce();
    const captured = setup.captureCharFrame();
    act(() => setup.renderer.destroy());

    expect(captured).toContain("no state yet");
    // It must not be the sentence QA rejected, and it must not be the branch's
    // own `sessions not provisioned`, which no gate ever reviewed.
    expect(captured).not.toContain("no session state");
    expect(captured).not.toContain("sessions not provisioned");
  });
});
