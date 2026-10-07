import { test } from "bun:test";
import { act } from "react";
import { testRender } from "@opentui/react/test-utils";
import { PaneFrame } from "./pane";
import { fxBlockLines, fxInk, fxPaneStatus, fxTone } from "./fx";
import type { ReadResult } from "../read";

/** QA probe for DIG-2071. Prints the real character frame of the fx-sessions
 * pane so the client-account pass rests on painted cells, not on formatters. */

const data = {
  sessions: [
    { session: "Asia", state: null, note: null },
    { session: "London", state: null, note: null },
    { session: "New York", state: null, note: null },
  ],
};

const result: ReadResult = {
  status: "ok",
  lines: ["source  static-sessions", "marks  unavailable"],
  asOf: null,
};

test("print fx-sessions pane", async () => {
  const now = "2026-10-07";
  const lines = fxBlockLines("fx-sessions", result, data);
  const tone = fxTone(result, lines, { now, data });
  const status = fxPaneStatus(result, data, "/fx/sessions", now);
  const ink = fxInk(tone);
  const setup = await testRender(
    <PaneFrame
      title="FX hub · sessions"
      status={status}
      focused={false}
      lines={lines}
      ink={ink}
    />,
    { width: 70, height: 8 },
  );
  await setup.renderOnce();
  const captured = setup.captureCharFrame();
  act(() => setup.renderer.destroy());
  console.log(`\n### tone=${tone} ink=${ink} lines=${JSON.stringify(lines)}`);
  console.log("### frame:");
  console.log(captured);
});