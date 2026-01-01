import { describe, expect, test } from "bun:test";

import {
  makeRecordedFrame,
  serializeRecordedFrame,
} from "../../../packages/tui-frame/src/record.ts";
import {
  cropChatPane,
  railColumns,
  TUI_SOURCE,
  DEFAULT_FRAME_WIDTH,
  WORDMARK_ROWS,
} from "./frame";

const RAIL = `${"s".repeat(27)}│`;

function header(): string[] {
  return Array.from({ length: WORDMARK_ROWS }, (_, index) => `wordmark row ${index}`);
}

function captured(rows: string[]): string {
  return [...header(), ...rows.map((row) => `${RAIL}${row}`)].join("\n");
}

describe("recorded frame geometry", () => {
  test("the rail width follows the app rule", () => {
    expect(railColumns(100)).toBe(28);
    expect(railColumns(60)).toBe(18);
    expect(railColumns(200)).toBe(28);
  });

  test("the crop drops the wordmark rows and the rail columns", () => {
    const cropped = cropChatPane(
      captured(["  chat thread", "  what is a recorded frame", "", ""]),
      { railCols: railColumns(DEFAULT_FRAME_WIDTH), headerRows: WORDMARK_ROWS },
    );
    expect(cropped.frame).toBe("  chat thread\n  what is a recorded frame");
    expect(cropped.frame).not.toContain("wordmark");
    expect(cropped.height).toBe(2);
    expect(cropped.width).toBe("  what is a recorded frame".length);
  });

  test("the crop keeps the banner rows when headerRows is not given", () => {
    const cropped = cropChatPane(captured(["  chat thread"]), {
      railCols: railColumns(DEFAULT_FRAME_WIDTH),
    });
    // The banner is not dropped: a row survives for each of the WORDMARK_ROWS
    // above the thread. It is full width and has no rail, so the rail crop
    // leaves only its right-hand part — the wordmark itself sits in the
    // columns the crop removes. This assertion used to check `wordmark row 0`
    // survived, which only held because a row shorter than the rail was
    // emitted whole: the leak this suite now refuses.
    const rows = cropped.frame.split("\n");
    expect(rows).toHaveLength(WORDMARK_ROWS + 1);
    expect(rows[WORDMARK_ROWS]).toBe("  chat thread");
    expect(cropped.frame).not.toContain("wordmark");
  });

  test("the crop strips the trailing spaces of a row", () => {
    const cropped = cropChatPane(captured(["  padded   "]), {
      railCols: railColumns(DEFAULT_FRAME_WIDTH),
      headerRows: WORDMARK_ROWS,
    });
    expect(cropped.frame).toBe("  padded");
  });

  test("a row shorter than the rail cannot leak a session title", () => {
    // The real client pads every row to the terminal width, but the crop must
    // not rely on that. An unpadded rail row carrying a session title is
    // shorter than `railCols`; it must still be cut away, not emitted whole.
    const railCols = railColumns(DEFAULT_FRAME_WIDTH);
    const unpadded = [
      ...header(),
      `${" ".repeat(railCols)}  chat thread`,
      "  book",
      "  desk",
    ].join("\n");
    const cropped = cropChatPane(unpadded, {
      railCols,
      headerRows: WORDMARK_ROWS,
    });
    expect(cropped.frame).toBe("  chat thread");
    expect(cropped.frame).not.toContain("book");
    expect(cropped.frame).not.toContain("desk");
  });

  test("the crop refuses a capture with no pane in it", () => {
    expect(() => cropChatPane("")).toThrow(/empty/);
    expect(() =>
      cropChatPane(captured([""]), {
        railCols: railColumns(DEFAULT_FRAME_WIDTH),
        headerRows: WORDMARK_ROWS,
      }),
    ).toThrow(/empty/);
  });
});

describe("the recorded frame record", () => {
  test("the record names the client, the pane, the time and the frame", () => {
    const record = makeRecordedFrame({
      source: TUI_SOURCE,
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

  test("the record's width and height describe the frame it carries", () => {
    const cropped = cropChatPane(captured(["  chat thread", "  and more"]), {
      railCols: railColumns(DEFAULT_FRAME_WIDTH),
      headerRows: WORDMARK_ROWS,
    });
    const record = makeRecordedFrame({
      source: TUI_SOURCE,
      path: "/thread",
      capturedAt: "2026-10-22T06:00:00.000Z",
      cropped,
    });
    expect(record.height).toBe(record.frame.split("\n").length);
    expect(record.width).toBe(
      Math.max(...record.frame.split("\n").map((row) => row.length)),
    );
  });

  test("the serializer writes stable JSON with a trailing newline", () => {
    const record = makeRecordedFrame({
      source: TUI_SOURCE,
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
