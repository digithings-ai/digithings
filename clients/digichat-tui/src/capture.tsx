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
 *
 * One fixture server per process. The client resolves its API base when its
 * module is evaluated (src/app.tsx:46), so the fixture URL has to be in the
 * environment before that import; the exporter keeps the server it started, so
 * every capture in one process reads the same URL and the CLI exits after its
 * single capture.
 */
import { act } from "react";
import { testRender } from "@opentui/react/test-utils";

import { makeRecordedFrame, type RecordedFrame } from "../../../packages/tui-frame/src/record.ts";
import {
  cropChatPane,
  railColumns,
  WORDMARK_ROWS,
  DEFAULT_FRAME_HEIGHT,
  DEFAULT_FRAME_WIDTH,
} from "./frame";
import { startFixtureApi, type FixtureApi } from "./fixture-api";
import { PLACEHOLDER, UNREACHABLE } from "./read";

// A recorded frame must not depend on animation timing.
process.env.DIGI_REDUCED_MOTION = "1";

/** The pane the exporter records: the chat thread. */
export const DEFAULT_PATH = "/thread";

let fixture: Promise<FixtureApi> | null = null;

/**
 * The process-wide fixture server.
 *
 * The client resolves its API base once, when its module is evaluated, so the
 * exporter keeps one server for the whole process: every capture in one test
 * process reads the same URL, and the server does not hold that process open.
 * The CLI is one-shot and exits after its capture.
 */
function sharedFixture(): Promise<FixtureApi> {
  fixture ??= startFixtureApi({ unref: true });
  return fixture;
}

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
  const api = await sharedFixture();
  // The client resolves its API base when its module is evaluated, so the
  // fixture URL is in the environment before the client module is loaded.
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
    // The composer is part of the thread screen, not of the fixture copy: a
    // frame without it recorded a loading or error screen.
    if (!cropped.frame.includes(PLACEHOLDER)) {
      throw new Error("the captured frame does not show the digichat thread");
    }
    return makeRecordedFrame({
      source: "digichat-tui",
      path: DEFAULT_PATH,
      capturedAt,
      cropped,
    });
  } finally {
    setup?.renderer.destroy();
    if (previousChatUrl === undefined) delete process.env.DIGI_CHAT_URL;
    else process.env.DIGI_CHAT_URL = previousChatUrl;
  }
}