/**
 * The shipped digichat TUI frame exporter (DIG-2698).
 *
 * ADR D7: the dashboard preview of a TUI is a recorded frame, not a live
 * socket. This renders the real client through the OpenTUI test harness,
 * captures the characters the client painted and records the chat pane.
 *
 * The frame is recorded against the fixture API (src/fixture-api.ts), never
 * against a live backend: a recorded frame must be the same on every run, and
 * it must never carry live customer data.
 */
import { act } from "react";
import { testRender } from "@opentui/react/test-utils";

import {
  cropMainPane,
  makeRecordedFrame,
  railColumns,
  DEFAULT_FRAME_HEIGHT,
  DEFAULT_FRAME_WIDTH,
  type RecordedFrame,
} from "./frame";
import { FIXTURE_API_URL, startFixtureApi } from "./fixture-api";
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
  // The client resolves its API base when its module is evaluated, so the
  // fixture URL is in the environment before the client module is loaded.
  process.env.DIGI_CHAT_URL = FIXTURE_API_URL;
  const api = startFixtureApi();
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
    const cropped = cropMainPane(captured, { railCols: railColumns(width) });
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
