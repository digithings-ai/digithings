import { describe, expect, test } from "bun:test";

import {
  isRecordedFrame,
  makeRecordedFrame,
  serializeRecordedFrame,
  type RecordedFrame,
} from "./record.ts";

const RECORD: RecordedFrame = {
  source: "digichat-tui",
  path: "/thread",
  capturedAt: "2026-10-22T05:45:00.000Z",
  width: 70,
  height: 40,
  frame: "a recorded frame",
};

describe("the recorded frame record", () => {
  test("makeRecordedFrame carries the crop's ink extent, not the terminal size", () => {
    const record = makeRecordedFrame({
      source: "digichat-tui",
      path: "/thread",
      capturedAt: "2026-10-22T05:45:00.000Z",
      cropped: { frame: "pane", width: 4, height: 1 },
    });
    expect(record).toEqual({
      source: "digichat-tui",
      path: "/thread",
      capturedAt: "2026-10-22T05:45:00.000Z",
      width: 4,
      height: 1,
      frame: "pane",
    });
  });

  test("the serializer writes stable JSON with a trailing newline", () => {
    const text = serializeRecordedFrame(RECORD);
    expect(text.endsWith("\n")).toBe(true);
    expect(JSON.parse(text)).toEqual(RECORD);
    // Key order is the type's order, so the same record writes the same bytes.
    expect(text.indexOf('"source"')).toBeLessThan(text.indexOf('"frame"'));
  });

  test("the same record serializes to the same bytes twice", () => {
    expect(serializeRecordedFrame(RECORD)).toBe(serializeRecordedFrame({ ...RECORD }));
  });
});

describe("the record guard", () => {
  test("it accepts a complete record", () => {
    expect(isRecordedFrame(RECORD)).toBe(true);
  });

  test("it refuses a missing field", () => {
    const { source, path, capturedAt, width, height, frame } = RECORD;
    expect(isRecordedFrame({ path, capturedAt, width, height, frame })).toBe(false);
    expect(isRecordedFrame({ source, capturedAt, width, height, frame })).toBe(false);
    expect(isRecordedFrame({ source, path, width, height, frame })).toBe(false);
    expect(isRecordedFrame({ source, path, capturedAt, height, frame })).toBe(false);
    expect(isRecordedFrame({ source, path, capturedAt, width, frame })).toBe(false);
    expect(isRecordedFrame({ source, path, capturedAt, width, height })).toBe(false);
  });

  test("it refuses a zero or non-numeric size", () => {
    expect(isRecordedFrame({ ...RECORD, width: 0 })).toBe(false);
    expect(isRecordedFrame({ ...RECORD, height: Number.NaN })).toBe(false);
    expect(isRecordedFrame({ ...RECORD, width: "70" })).toBe(false);
  });

  test("it refuses an empty frame and an empty label", () => {
    expect(isRecordedFrame({ ...RECORD, frame: "" })).toBe(false);
    expect(isRecordedFrame({ ...RECORD, source: "" })).toBe(false);
    expect(isRecordedFrame({ ...RECORD, path: "" })).toBe(false);
  });

  test("it refuses a capture time with no zone", () => {
    // An offset-less timestamp reads in the local zone, so the server render
    // and the client hydration would label the same frame differently.
    expect(isRecordedFrame({ ...RECORD, capturedAt: "2026-10-22T05:45:00.000" })).toBe(
      false,
    );
    expect(isRecordedFrame({ ...RECORD, capturedAt: "2026-10-22 05:45" })).toBe(false);
    expect(isRecordedFrame({ ...RECORD, capturedAt: "" })).toBe(false);
  });

  test("it refuses a value that is not a record", () => {
    expect(isRecordedFrame(null)).toBe(false);
    expect(isRecordedFrame("frame")).toBe(false);
    expect(isRecordedFrame([])).toBe(false);
  });
});
