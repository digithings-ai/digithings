/**
 * Recorded-frame helpers for the digichat terminal client (DIG-2698).
 *
 * ADR D7 ("Dashboard previews"): TUI previews are not live sockets in 1.0.
 * Each TUI exports recorded frames with OpenTUI `captureCharFrame()` and the
 * dashboard renders them as text in Geist Mono. The frame is data: it is
 * rendered byte-for-byte, never interpreted.
 *
 * The client paints a left rail (the session list) and the chat thread to its
 * right (src/app.tsx:397,470,484). The rail is `min(28, max(18, floor(width *
 * 0.28)))` columns wide and its right border sits in the last rail column, so
 * the thread starts at column `rail`.
 */

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
): { frame: string; width: number; height: number } {
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
