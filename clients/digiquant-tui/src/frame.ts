/**
 * D9 recorded-frame export: the digiquant TUI (DIG-2698).
 *
 * ADR D7: TUI previews are not live sockets in 1.0. Each TUI exports recorded
 * frames with OpenTUI `captureCharFrame()`, and the dashboard renders them as
 * text in Geist Mono. This module owns the recorded-frame record and the crop
 * that takes the main desk pane out of a captured frame. It is pure: the
 * renderer harness lives in `capture.tsx`, so the record shape and the crop
 * are testable without a terminal.
 *
 * The frame is data. It is cropped and carried, never interpreted.
 */

import { MARK_ROWS } from './mark';
import { RAIL_COLS_DEFAULT } from './rail';

/** The rail width the crop assumes, re-exported so the crop and its test read one number. */
export { RAIL_COLS_DEFAULT };

/** Which TUI a recorded frame came from. */
export const TUI_SOURCE = 'digiquant-tui';

/** A recorded frame, as the exporter writes it and the dashboard reads it. */
export type RecordedFrame = {
  /** Which TUI the frame was recorded from. */
  source: string;
  /** The desk path the frame shows (`/brief`). */
  path: string;
  /** ISO timestamp of the capture. */
  capturedAt: string;
  /** Columns in the cropped frame. */
  width: number;
  /** Rows in the cropped frame. */
  height: number;
  /** The cropped frame, exactly as captured. */
  frame: string;
};

/** Terminal size the exporter records at. Matches the app-key test harness. */
export const DEFAULT_FRAME_WIDTH = 100;
export const DEFAULT_FRAME_HEIGHT = 30;

/**
 * Rows above the desk body: the header band (`MARK_ROWS`) and its rule row.
 * The desk body is what the matrix D9 row calls the main desk pane.
 */
export const HEADER_ROWS = MARK_ROWS + 1;

export type CropOptions = {
  /** Columns the rail occupies (default 36, `RAIL_COLS_DEFAULT`). */
  railCols?: number;
  /** Rows above the desk body (default `HEADER_ROWS`). */
  headerRows?: number;
};

export type CroppedFrame = {
  /** The cropped frame. */
  frame: string;
  /** Columns in the cropped frame. */
  width: number;
  /** Rows in the cropped frame. */
  height: number;
};

/**
 * Take the main desk pane out of a captured frame.
 *
 * The desk draws a header band, a rule, then a row that holds the rail on the
 * left and the desk body on the right, then a footer rule. The body is the
 * pane: the rail is the page list beside it, not part of it. So the crop drops
 * the rows above the body and the footer rule, and the columns the rail
 * occupies.
 *
 * Trailing blanks are trimmed per row: the pane is narrower than the
 * terminal on most rows, and the blanks carry no content.
 */
export function cropMainDeskPane(captured: string, options: CropOptions = {}): CroppedFrame {
  const railCols = options.railCols ?? RAIL_COLS_DEFAULT;
  const headerRows = options.headerRows ?? HEADER_ROWS;

  const lines = captured.split('\n');
  // `captureCharFrame()` ends the frame with a newline; the empty tail is not a row.
  if (lines.length > 0 && lines[lines.length - 1] === '') lines.pop();
  // The footer rule is the last row of the desk, so the body stops one row short.
  const body = lines.slice(headerRows, Math.max(headerRows, lines.length - 1));

  const cropped = body.map((line) => line.slice(railCols).replace(/[ \t]+$/, ''));
  while (cropped.length > 0 && cropped[cropped.length - 1] === '') cropped.pop();

  const width = cropped.reduce((widest, line) => Math.max(widest, line.length), 0);
  if (cropped.length === 0 || width === 0) {
    // A silent empty crop would be written as a record with no frame, and the
    // dashboard's shape guard would drop it — the preview would just vanish.
    throw new Error(
      `the main desk pane crop is empty (${width}x${cropped.length} columns and rows)`,
    );
  }
  return { frame: cropped.join('\n'), width, height: cropped.length };
}

/** Build the record the exporter writes. */
export function makeRecordedFrame(args: {
  source: string;
  path: string;
  capturedAt: string;
  cropped: CroppedFrame;
}): RecordedFrame {
  return {
    source: args.source,
    path: args.path,
    capturedAt: args.capturedAt,
    width: args.cropped.width,
    height: args.cropped.height,
    frame: args.cropped.frame,
  };
}

/** The on-disk form of a record: JSON, one key per line, trailing newline. */
export function serializeRecordedFrame(record: RecordedFrame): string {
  return `${JSON.stringify(record, null, 2)}\n`;
}
