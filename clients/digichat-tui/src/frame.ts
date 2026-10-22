/**
 * Recorded-frame helpers for the digichat terminal client (DIG-2698).
 *
 * ADR D7 ("Dashboard previews"): TUI previews are not live sockets in 1.0.
 * Each TUI exports recorded frames with OpenTUI `captureCharFrame()` and the
 * dashboard renders them as text in Geist Mono. The frame is data: it is
 * rendered byte-for-byte, never interpreted.
 *
 * The client paints the wordmark banner at the top of the screen (full width)
 * and below it a left rail with the session list, with the chat thread to
 * the rail's right (src/app.tsx:468-484). The recorded frame is the chat
 * pane: the banner rows are dropped and the rail columns are cropped away.
 * The rail width and the banner height come from src/layout.ts, the same
 * module the client itself uses, so the crop cannot drift from the screen.
 */

import { railColumns, WORDMARK_ROWS } from "./layout";

export const TUI_SOURCE = "digichat-tui";

export type RecordedFrame = {
  source: string;
  path: string;
  capturedAt: string;
  width: number;
  height: number;
  frame: string;
};

export const DEFAULT_FRAME_WIDTH = 100;
export const DEFAULT_FRAME_HEIGHT = 40;

export { railColumns, WORDMARK_ROWS };

/**
 * Crop a captured frame to the main chat pane: drop the wordmark rows, drop
 * the rail columns, strip the trailing spaces each row leaves behind and drop
 * the trailing empty rows.
 */
export function cropChatPane(
  captured: string,
  options?: { railCols?: number; headerRows?: number },
): { frame: string; width: number; height: number } {
  const railCols = options?.railCols ?? 0;
  const headerRows = options?.headerRows ?? 0;
  const kept = captured
    .split("\n")
    .slice(headerRows)
    .map((row) => row.slice(railCols).replace(/\s+$/, ""));
  while (kept.length > 0 && kept[kept.length - 1] === "") kept.pop();
  const width = kept.reduce((widest, row) => Math.max(widest, row.length), 0);
  if (kept.length === 0 || width === 0) {
    throw new Error(
      `the chat pane crop is empty (${kept.length} rows, ${width} columns)`,
    );
  }
  return { frame: kept.join("\n"), width, height: kept.length };
}

/** Build the record the dashboard reads (ADR D7: recorded frames only). */
export function makeRecordedFrame(input: {
  source?: string;
  path: string;
  capturedAt: string;
  cropped: { frame: string; width: number; height: number };
}): RecordedFrame {
  return {
    source: input.source ?? TUI_SOURCE,
    path: input.path,
    capturedAt: input.capturedAt,
    width: input.cropped.width,
    height: input.cropped.height,
    frame: input.cropped.frame,
  };
}

/** Serialize a record for the dashboard fixture (stable key order, newline). */
export function serializeRecordedFrame(record: RecordedFrame): string {
  return `${JSON.stringify(record, null, 2)}\n`;
}
