/**
 * Recorded-frame helpers for the digichat terminal client (DIG-2698).
 *
 * ADR D7 ("Dashboard previews"): TUI previews are not live sockets in 1.0.
 * Each TUI exports recorded frames with OpenTUI `captureCharFrame()` and the
 * dashboard renders them as text in Geist Mono. The frame is data: it is
 * rendered byte-for-byte, never interpreted.
 *
 * The record itself is declared once, in `packages/tui-frame`, and shared with
 * the digiquant client and the dashboard. This module adds only what is
 * specific to the digichat client: its source label, the terminal size it
 * records at and the crop that takes the chat thread out of a captured frame.
 * It does not re-export the record — a second export surface is how the copies
 * drifted before.
 *
 * The client paints the wordmark banner at the top of the screen (full width)
 * and below it a left rail with the session list, with the chat thread to
 * the rail's right (src/app.tsx). The recorded frame is the chat pane: the
 * banner rows are dropped and the rail columns are cropped away. The rail
 * width and the banner height come from src/layout.ts, the same module the
 * client itself uses, so the crop cannot drift from the screen.
 */

import type { CroppedFrame } from "../../../packages/tui-frame/src/record.ts";

import { railColumns, WORDMARK_ROWS } from "./layout";

export { railColumns, WORDMARK_ROWS };

export const TUI_SOURCE = "digichat-tui";

export const DEFAULT_FRAME_WIDTH = 100;
export const DEFAULT_FRAME_HEIGHT = 40;

/**
 * Crop a captured frame to the chat pane: drop the wordmark rows, drop the
 * rail columns, strip the trailing spaces each row leaves behind and drop the
 * trailing empty rows.
 */
export function cropChatPane(
  captured: string,
  options?: { railCols?: number; headerRows?: number },
): CroppedFrame {
  const railCols = options?.railCols ?? 0;
  const headerRows = options?.headerRows ?? 0;
  const kept = captured
    .split("\n")
    .slice(headerRows)
    .map((row) => {
      const sliced = row.length >= railCols ? row.slice(railCols) : row;
      return sliced.replace(/\s+$/, "");
    });
  while (kept.length > 0 && kept[kept.length - 1] === "") kept.pop();
  const width = kept.reduce((widest, row) => Math.max(widest, row.length), 0);
  if (kept.length === 0 || width === 0) {
    throw new Error(
      `the chat pane crop is empty (${kept.length} rows, ${width} columns)`,
    );
  }
  return { frame: kept.join("\n"), width, height: kept.length };
}

/** Backwards-compatible alias for the old crop name. */
export const cropMainPane = cropChatPane;