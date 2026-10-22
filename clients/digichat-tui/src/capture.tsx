/**
 * The shipped digichat TUI frame exporter (DIG-2698).
 *
 * ADR D7: the dashboard preview of a TUI is a recorded frame, not a live
 * socket. This renders the real client through the OpenTUI test harness,
 * captures the characters the client painted and records the chat pane.
 *
 * The frame is recorded against the fixture API (src/fixture-api.ts), never
 * against a live backend: a recorded frame must be the same on every run, and
 * it must never carry live customer data. Two guards keep that true:
 *   - the client must have read from the fixture (the fixture counts the
 *     requests it served) — the client resolves its API base when its module
 *     is evaluated, so a client module that was loaded earlier would talk to
 *     that other backend instead;
 *   - the frame must carry the fixture's own text.
 * Either guard failing refuses the capture, so no frame is written.
 */
import { act } from "react";
import { testRender } from "@opentui/react/test-utils";

import {
  cropChatPane,
  makeRecordedFrame,
  railColumns,
  WORDMARK_ROWS,
  DEFAULT_FRAME_HEIGHT,
  DEFAULT_FRAME_WIDTH,
  type RecordedFrame,
} from "./frame";
import { startFixtureApi } from "./fixture-api";
import { UNREACHABLE } from "./read";

// A recorded frame must not depend on animation timing.
process.env.DIGI_REDUCED_MOTION = "1";

/** The pane the exporter records: the chat thread. */
export const DEFAULT_PATH = "/thread";

/** A word the fixture thread always paints, used to refuse an empty frame. */
export const CAPTURE_MARKER = "captureCharFrame";

/**
 * Render the client, wait for the thread to load and record the chat pane.
 */
export async function captureChatThread(options?: {
  width?: number;
  height?: number;
  capturedAt?: string;
}): Promise<RecordedFrame> {
  const width = options?.width ?? DEFAULT_FRAME_WIDTH;
  const height = options?.height ?? DEFAULT_FRAME_HEIGHT;
  const capturedAt = options?.capturedAt ?? new Date().toISOString();
  const previousChatUrl = process.env.DIGI_CHAT_URL;
  const api = startFixtureApi();
  // The client resolves its API base when its module is evaluated
  // (src/app.tsx:46), so the fixture URL is in the environment before the
  // client module is loaded.
  process.env.DIGI_CHAT_URL = api.url;
  let setup: Awaited<ReturnType<typeof testRender>> | null = null;
  try {
    const { App } = await import("./app");
    setup = await testRender(<App />, { width, height });
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 400));
    });
    await setup.flush();
    const captured = setup.captureCharFrame();
    if (captured.includes(UNREACHABLE)) {
      throw new Error("the digichat thread did not load from the fixture API");
    }
    if (api.served() === 0) {
      throw new Error(
        "the digichat client did not read from the fixture API; the recorded frame would be live data",
      );
    }
    const cropped = cropChatPane(captured, {
      railCols: railColumns(width),
      headerRows: WORDMARK_ROWS,
    });
    if (!cropped.frame.includes(CAPTURE_MARKER)) {
      throw new Error("the captured frame does not show the chat thread");
    }
    return makeRecordedFrame({
      path: DEFAULT_PATH,
      capturedAt,
      cropped,
    });
  } finally {
    setup?.renderer.destroy();
    api.close();
    if (previousChatUrl === undefined) delete process.env.DIGI_CHAT_URL;
    else process.env.DIGI_CHAT_URL = previousChatUrl;
  }
}
