/**
 * Recorded-frame helpers for the digivoice terminal client (DIG-2698).
 *
 * ADR D7: TUI previews are not live sockets in 1.0. Each TUI exports recorded
 * frames with OpenTUI `captureCharFrame()`, and the dashboard renders them as
 * text in Geist Mono. The record itself is declared once, in
 * `packages/tui-frame`, and shared with the other clients and the dashboard.
 * This module adds what is specific to this client: its source label, the
 * terminal size it records at and the crop that takes the main setup pane out
 * of a captured frame. It is pure: the renderer harness lives in
 * `capture.tsx`, so the crop is testable without a terminal.
 *
 * The frame is data. It is cropped and carried, never interpreted.
 */
import type { CroppedFrame } from "../../../packages/tui-frame/src/record.ts";

/** Which TUI a recorded frame came from. */
export const TUI_SOURCE = "digivoice-tui";

/** Terminal size the exporter records at. */
export const DEFAULT_FRAME_WIDTH = 100;
export const DEFAULT_FRAME_HEIGHT = 30;

/**
 * Rows above the setup body: the wordmark (`WORDMARK_ROWS` = 5) plus the
 * status strip (1).
 */
export const HEADER_ROWS = 5 + 1;

/**
 * Rows below the setup body: the status line, the key-hint line and the
 * two-row credit footer.
 */
export const FOOTER_ROWS = 1 + 1 + 2;

/** Columns the left setup menu (rail) occupies. Mirrors app.tsx. */
export function railColumns(width: number): number {
  return Math.min(34, Math.max(22, Math.floor(width * 0.3)));
}

export type CropOptions = {
  railCols?: number;
  headerRows?: number;
  footerRows?: number;
};

/**
 * Take the main setup pane out of a captured frame: drop the header band, the
 * left menu rail and the footer rule, then trim trailing blanks.
 */
export function cropMainPane(captured: string, options: CropOptions = {}): CroppedFrame {
  const railCols = options.railCols ?? railColumns(DEFAULT_FRAME_WIDTH);
  const headerRows = options.headerRows ?? HEADER_ROWS;
  const footerRows = options.footerRows ?? FOOTER_ROWS;

  const lines = captured.split("\n");
  if (lines.length > 0 && lines[lines.length - 1] === "") lines.pop();
  const bodyEnd = Math.max(headerRows, lines.length - footerRows);
  const body = lines.slice(headerRows, bodyEnd);

  const cropped = body.map((line) => line.slice(railCols).replace(/[ \t]+$/, ""));
  while (cropped.length > 0 && cropped[cropped.length - 1] === "") cropped.pop();

  const width = cropped.reduce((widest, line) => Math.max(widest, line.length), 0);
  if (cropped.length === 0 || width === 0) {
    throw new Error(
      `the main setup pane crop is empty (${width}x${cropped.length} columns and rows)`,
    );
  }
  return { frame: cropped.join("\n"), width, height: cropped.length };
}