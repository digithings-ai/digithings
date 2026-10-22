/**
 * Recorded-frame helpers for the digichat terminal client (DIG-2698).
 *
 * ADR D7 ("Dashboard previews"): TUI previews are not live sockets in 1.0.
 * Each TUI exports recorded frames with OpenTUI `captureCharFrame()` and the
 * dashboard renders them as text in Geist Mono. The frame is data: it is
 * rendered byte-for-byte, never interpreted.
 *
 * The record itself is declared once, in `packages/tui-frame`, and shared with
 * the digiquant client and the dashboard. This module adds what is specific to
 * the digichat client: its source label, the terminal size it records at and
 * the crop that takes the chat thread out of a captured frame.
 *
 * The client paints a left rail (the session list) and the chat thread to its
 * right (src/app.tsx:397,470,484). The rail is `min(28, max(18, floor(width *
 * 0.28)))` columns wide and its right border sits in the last rail column, so
 * the thread starts at column `rail`.
 */

import type { CroppedFrame } from "../../../packages/tui-frame/src/record.ts";

export {
  makeRecordedFrame,
  serializeRecordedFrame,
  type RecordedFrame,
} from "../../../packages/tui-frame/src/record.ts";

export const TUI_SOURCE = "digichat-tui";

export const DEFAULT_FRAME_WIDTH = 100;
export const DEFAULT_FRAME_HEIGHT = 40;

/** The rail width in columns — the same rule the app uses (src/app.tsx:397). */
export function railColumns(width: number): number {
  return Math.min(28, Math.max(18, Math.floor(width * 0.28)));
}

/**
 * Crop a captured frame to the main chat pane: drop the rail columns, strip
 * the trailing spaces each row leaves behind and drop the trailing empty rows.
 */
export function cropMainPane(
  captured: string,
  options?: { railCols?: number },
): CroppedFrame {
  const railCols = options?.railCols ?? 0;
  const kept = captured
    .split("\n")
    .map((row) => row.slice(railCols).replace(/\s+$/, ""));
  while (kept.length > 0 && kept[kept.length - 1] === "") kept.pop();
  const width = kept.reduce((widest, row) => Math.max(widest, row.length), 0);
  if (kept.length === 0 || width === 0) {
    throw new Error(
      `the main chat pane crop is empty (${kept.length} rows, ${width} columns)`,
    );
  }
  return { frame: kept.join("\n"), width, height: kept.length };
}
