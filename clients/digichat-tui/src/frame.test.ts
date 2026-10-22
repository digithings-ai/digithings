import { describe, expect, test } from "bun:test";

import {
  cropMainPane,
  makeRecordedFrame,
  railColumns,
  serializeRecordedFrame,
  TUI_SOURCE,
  DEFAULT_FRAME_WIDTH,
} from "./frame";

const RAIL = `${"s".repeat(27)}│`;

function captured(rows: string[]): string {
  return rows.map((row) => `${RAIL}${row}`).join("\n");
}

describe("recorded frame geometry", () => {
  test("the rail width follows the app rule", () => {
    expect(railColumns(100)).toBe(28);
    expect(railColumns(60)).toBe(18);
    expect(railColumns(200)).toBe(28);
  });

  test("the crop drops the rail columns and the trailing empty rows", () => {
    const cropped = cropMainPane(
      captured(["  chat thread", "  what is a recorded frame", "", ""]),
      { railCols: railColumns(DEFAULT_FRAME_WIDTH) },
    );
    expect(cropped.frame).toBe("  chat thread\n  what is a recorded frame");
    expect(cropped.height).toBe(2);
    expect(cropped.width).toBe("  what is a recorded frame".length);
  });

  test("the crop strips the trailing spaces of a row", () => {
    const cropped = cropMainPane(captured(["  padded   "]), {
      railCols: railColumns(DEFAULT_FRAME_WIDTH),
    });
    expect(cropped.frame).toBe("  padded");
  });

  test("the crop refuses a capture with no pane in it", () => {
    expect(() => cropMainPane("")).toThrow(/empty/);
    expect(() =>
      cropMainPane(captured([""]), { railCols: railColumns(DEFAULT_FRAME_WIDTH) }),
    ).toThrow(/empty/);
  });
});

describe("the recorded frame record", () => {
  test("the record names the client, the pane, the time and the frame", () => {
    const record = makeRecordedFrame({
      path: "/thread",
      capturedAt: "2026-10-22T06:00:00.000Z",
      cropped: { frame: "chat thread", width: 11, height: 1 },
    });
    expect(record.source).toBe(TUI_SOURCE);
    expect(record.path).toBe("/thread");
    expect(record.capturedAt).toBe("2026-10-22T06:00:00.000Z");
    expect(record.width).toBe(11);
    expect(record.height).toBe(1);
    expect(record.frame).toBe("chat thread");
  });

  test("the serializer writes stable JSON with a trailing newline", () => {
    const record = makeRecordedFrame({
      path: "/thread",
      capturedAt: "2026-10-22T06:00:00.000Z",
      cropped: { frame: "chat thread", width: 11, height: 1 },
    });
    const text = serializeRecordedFrame(record);
    expect(text.endsWith("\n")).toBe(true);
    expect(JSON.parse(text)).toEqual(record);
    expect(text).toContain('"source": "digichat-tui"');
  });
});
