/**
 * D9 recorded-frame capture: the digiquant TUI (DIG-2698).
 *
 * The shipped exporter. ADR D7: each TUI exports recorded frames with OpenTUI
 * `captureCharFrame()` — the same capture the app-key tests read — and the
 * dashboard renders them as text in Geist Mono. No live socket, no CSP change.
 *
 * The harness is the test renderer because it is the only renderer in the repo
 * that paints to a fixed-size grid without a terminal device. The recorded
 * frame is what a terminal would show, so the crop in `frame.ts` is taken from
 * a real render, never from a mock.
 *
 * The capture reads the desk through the fixture API (`./fixture-api`, imported
 * first so the client reads the fixture and not a live desk), and it waits for
 * the desk's reads to land before it records. A capture taken while the blocks
 * are still loading records placeholders, not the desk — and the artifact it
 * writes would be a terminal full of error lines.
 */

import { act } from 'react';
import { testRender } from '@opentui/react/test-utils';
// The fixture API has to be imported before the app: the client reads its API
// base when its module is evaluated.
import { assertFixtureBase, startFixtureApi } from './fixture-api';
import { App } from './app';
import {
  cropMainDeskPane,
  DEFAULT_FRAME_HEIGHT,
  DEFAULT_FRAME_WIDTH,
  makeRecordedFrame,
  TUI_SOURCE,
  type RecordedFrame,
} from './frame';

/** The path the desk opens on. */
export const DEFAULT_DESK_PATH = '/brief';

/** What a block paints while its read is in flight. */
const LOADING_MARK = 'loading…';

/** What the client paints when the API cannot be reached at all. */
const UNREACHABLE_MARK = 'could not be reached';

export type CaptureOptions = {
  /** Desk path to record (`/brief`). */
  path?: string;
  /** Terminal columns to render at. */
  width?: number;
  /** Terminal rows to render at. */
  height?: number;
  /** ISO timestamp of the capture. Defaults to now. */
  capturedAt?: string;
};

/** How many settle passes to give the desk's reads before the capture gives up. */
const SETTLE_ATTEMPTS = 120;

/** How long to wait between settle passes. */
const SETTLE_DELAY_MS = 25;

type Setup = Awaited<ReturnType<typeof testRender>>;

/**
 * Render the desk, let its reads land, and record the main desk pane.
 *
 * The desk opens on `/brief`; another path is reached through the path
 * palette (`/`, the path, enter), the same keys the app-key tests use.
 */
export async function captureDeskPane(options: CaptureOptions = {}): Promise<RecordedFrame> {
  const path = options.path ?? DEFAULT_DESK_PATH;
  const width = options.width ?? DEFAULT_FRAME_WIDTH;
  const height = options.height ?? DEFAULT_FRAME_HEIGHT;

  assertFixtureBase();
  const fixture = await startFixtureApi();
  const argv = process.argv;
  try {
    // The desk takes its start page from the command line (`app.tsx`), so the
    // exporter sets it explicitly. Otherwise an exporter flag that happens to
    // look like a desk path would steer the render, and the record would name
    // a page the frame does not show.
    process.argv = [argv[0] ?? 'digiquant-tui', path];

    const setup = await testRender(<App />, { width, height });
    try {
      // Two passes: the first lays the body out and measures it, the second
      // paints the face that fits.
      await act(async () => {
        await setup.renderOnce();
      });
      await act(async () => {
        await setup.renderOnce();
      });

      if (path !== DEFAULT_DESK_PATH) {
        await act(async () => {
          setup.mockInput.typeText('/');
        });
        await act(async () => {
          await setup.renderOnce();
        });
        await act(async () => {
          setup.mockInput.typeText(path.replace(/^\//, ''));
        });
        await act(async () => {
          await setup.renderOnce();
        });
        await act(async () => {
          setup.mockInput.pressEnter();
        });
        await act(async () => {
          await setup.renderOnce();
        });
      }

      const captured = await settledFrame(setup, path);
      const cropped = cropMainDeskPane(captured);
      return makeRecordedFrame({
        source: TUI_SOURCE,
        path,
        capturedAt: options.capturedAt ?? new Date().toISOString(),
        cropped,
      });
    } finally {
      act(() => setup.renderer.destroy());
    }
  } finally {
    process.argv = argv;
    await fixture.close();
  }
}

/**
 * Wait for the desk's reads to land, then hand back the frame.
 *
 * A block paints "loading…" until its fetch resolves, so the capture has to
 * wait for the state to change and re-render. It then checks the frame says
 * what it should: no loading block left, no unreachable-API line, and a header
 * that names the page the record claims.
 */
async function settledFrame(setup: Setup, path: string): Promise<string> {
  let frame = setup.captureCharFrame();
  for (let attempt = 0; attempt < SETTLE_ATTEMPTS && frame.includes(LOADING_MARK); attempt += 1) {
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, SETTLE_DELAY_MS));
      await setup.flush();
      await setup.renderOnce();
    });
    frame = setup.captureCharFrame();
  }
  if (frame.includes(LOADING_MARK)) {
    throw new Error(`the desk did not settle: ${path} still paints a loading block`);
  }
  if (frame.includes(UNREACHABLE_MARK)) {
    throw new Error(`the desk API was not readable: ${path} paints "${UNREACHABLE_MARK}"`);
  }
  const header = frame.split('\n').find((line) => line.includes('desk:'));
  if (!header || !header.includes(path)) {
    throw new Error(
      `the desk did not open ${path}: the header reads ${JSON.stringify(header ?? '')}`,
    );
  }
  return frame;
}
