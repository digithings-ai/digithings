/**
 * The recorded-TUI-frame record (DIG-2698, ADR D7).
 *
 * This is the single declaration of the record. Both TUI exporters write it
 * and the dashboard reads it; before this package each side declared its own
 * copy and the copies drifted (the dashboard called `width` the terminal
 * width while the producers wrote the ink extent of the crop).
 *
 * The frame is data: it is cropped, carried and rendered byte-for-byte, never
 * interpreted.
 */

/** One recorded terminal frame, exactly as the exporter wrote it. */
export type RecordedFrame = {
  /** Which TUI the frame was recorded from (label only). */
  source: string;
  /** The screen the frame shows (e.g. `/brief`, `/thread`). */
  path: string;
  /**
   * ISO timestamp of the capture, with an explicit zone (`Z` or `±HH:MM`).
   * An offset-less timestamp reads in the machine's local zone, so the server
   * render and the client hydration would label the same frame differently.
   */
  capturedAt: string;
  /**
   * Columns of ink in the cropped frame — the extent of the widest kept row,
   * not the terminal width. A 100-column terminal whose pane ends at column 70
   * records 70.
   */
  width: number;
  /** Rows of ink in the cropped frame — the terminal height minus nothing kept. */
  height: number;
  /** The cropped frame, exactly as captured. */
  frame: string;
};

/** The crop a client makes before it writes a record. */
export type CroppedFrame = {
  /** The cropped frame. */
  frame: string;
  /** Columns in the cropped frame. */
  width: number;
  /** Rows in the cropped frame. */
  height: number;
};

/** Build the record an exporter writes and the dashboard reads. */
export function makeRecordedFrame(input: {
  source: string;
  path: string;
  capturedAt: string;
  cropped: CroppedFrame;
}): RecordedFrame {
  return {
    source: input.source,
    path: input.path,
    capturedAt: input.capturedAt,
    width: input.cropped.width,
    height: input.cropped.height,
    frame: input.cropped.frame,
  };
}

/**
 * Serialize a record for the committed fixture: stable key order (the type's
 * own order) and a trailing newline. Two captures with the same `capturedAt`
 * therefore write the same bytes.
 */
export function serializeRecordedFrame(record: RecordedFrame): string {
  return `${JSON.stringify(record, null, 2)}\n`;
}

/** A capture time must carry an explicit zone (`Z` or `±HH:MM`). */
const ZONED_ISO = /(?:Z|[+-]\d{2}:?\d{2})$/i;

/** True when the value is a complete recorded frame. */
export function isRecordedFrame(value: unknown): value is RecordedFrame {
  if (!value || typeof value !== "object") return false;
  const record = value as Partial<RecordedFrame>;
  return (
    typeof record.source === "string" &&
    record.source.trim() !== "" &&
    typeof record.path === "string" &&
    record.path.trim() !== "" &&
    typeof record.capturedAt === "string" &&
    record.capturedAt.trim() !== "" &&
    ZONED_ISO.test(record.capturedAt.trim()) &&
    typeof record.width === "number" &&
    Number.isFinite(record.width) &&
    record.width > 0 &&
    typeof record.height === "number" &&
    Number.isFinite(record.height) &&
    record.height > 0 &&
    typeof record.frame === "string" &&
    record.frame.length > 0
  );
}
