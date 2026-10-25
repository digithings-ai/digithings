/**
 * The shipped digivoice TUI frame exporter (DIG-2698).
 *
 * ADR D7 ("Dashboard previews"): the dashboard preview of a TUI is a recorded
 * frame, not a live socket. This renders the real client through the OpenTUI
 * test harness, captures the characters the client painted and records the
 * setup pane.
 *
 * The frame is recorded against the fixture CLI (src/fixture-cli.ts), never
 * against a live backend: a recorded frame must be the same on every run.
 *
 * The client resolves its CLI prefix when its module is evaluated (src/read.ts),
 * so `DIGIVOICE_BIN` has to be in the environment before that import.
 */
import { act } from "react";
import { testRender } from "@opentui/react/test-utils";

import { makeRecordedFrame, type RecordedFrame } from "../../../packages/tui-frame/src/record.ts";
import {
  cropMainPane,
  railColumns,
  DEFAULT_FRAME_HEIGHT,
  DEFAULT_FRAME_WIDTH,
  TUI_SOURCE,
} from "./frame";
import { FIXTURE_CLI } from "./fixture-api";

// A recorded frame must not depend on animation timing.
process.env.DIGI_REDUCED_MOTION = "1";

/** The pane the exporter records: the setup screen. */
export const DEFAULT_PATH = "/setup";

/** The client paints this when it cannot reach its CLI. */
const UNREACHABLE = "not reachable";

/** The header the setup pane paints; the crop proves it is the right screen. */
const PANE_MARK = "DigiVoice";

/**
 * Render the client, wait for the fixture CLI to answer and record the setup
 * pane.
 */
export async function captureSetupPane(options?: {
  width?: number;
  height?: number;
  capturedAt?: string;
}): Promise<RecordedFrame> {
  const width = options?.width ?? DEFAULT_FRAME_WIDTH;
  const height = options?.height ?? DEFAULT_FRAME_HEIGHT;
  const capturedAt = options?.capturedAt ?? new Date().toISOString();
  const previousBin = process.env.DIGIVOICE_BIN;
  // The client resolves its CLI prefix when its module is evaluated, so the
  // fixture path is in the environment before the client module is loaded.
  process.env.DIGIVOICE_BIN = `${process.execPath} ${FIXTURE_CLI}`;
  let setup: Awaited<ReturnType<typeof testRender>> | null = null;
  try {
    const { App } = await import("./app");
    setup = await testRender(<App />, { width, height });
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 500));
    });
    await setup.flush();
    const captured = setup.captureCharFrame();
    if (captured.includes(UNREACHABLE)) {
      throw new Error("the digivoice setup did not load from the fixture CLI");
    }
    const cropped = cropMainPane(captured, { railCols: railColumns(width) });
    // A frame without the setup header recorded a loading or error screen.
    if (!cropped.frame.includes(PANE_MARK)) {
      throw new Error("the captured frame does not show the digivoice setup");
    }
    return makeRecordedFrame({
      source: TUI_SOURCE,
      path: DEFAULT_PATH,
      capturedAt,
      cropped,
    });
  } finally {
    setup?.renderer.destroy();
    if (previousBin === undefined) delete process.env.DIGIVOICE_BIN;
    else process.env.DIGIVOICE_BIN = previousBin;
  }
}
