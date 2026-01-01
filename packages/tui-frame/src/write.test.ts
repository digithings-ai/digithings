import { expect, test } from "bun:test";
import { mkdtemp, readFile, stat } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

import {
  isRecordedFrame,
  makeRecordedFrame,
  serializeRecordedFrame,
  type RecordedFrame,
} from "./record";
import { writeRecordedFrame } from "./write";

const RECORD = makeRecordedFrame({
  source: "digichat-tui",
  path: "/thread",
  capturedAt: "2026-10-22T06:00:00.000Z",
  cropped: { frame: "  chat thread\n  recorded", width: 17, height: 2 },
});

/** The committed fixtures the dashboard ships today. */
const FIXTURES = [
  new URL("../../../apps/dashboard/fixtures/tui-frames/digichat-tui.json", import.meta.url),
  new URL("../../../apps/dashboard/fixtures/tui-frames/digiquant-tui.json", import.meta.url),
  new URL("../../../clients/digichat-tui/fixtures/digichat-tui.json", import.meta.url),
];

test("the writer creates the parent directory and writes the serialized bytes", async () => {
  const dir = await mkdtemp(join(tmpdir(), "tui-frame-write-"));
  const out = join(dir, "nested", "deeper", "frame.json");
  await writeRecordedFrame(out, RECORD);
  expect(await readFile(out, "utf8")).toBe(serializeRecordedFrame(RECORD));
});

test("a written record reads back as the same record", async () => {
  const dir = await mkdtemp(join(tmpdir(), "tui-frame-write-"));
  const out = join(dir, "frame.json");
  await writeRecordedFrame(out, RECORD);
  const parsed: unknown = JSON.parse(await readFile(out, "utf8"));
  expect(isRecordedFrame(parsed)).toBe(true);
  expect(parsed).toEqual(RECORD);
});

test("the writer refuses a record the dashboard would drop", async () => {
  const dir = await mkdtemp(join(tmpdir(), "tui-frame-write-"));
  const out = join(dir, "frame.json");
  const blank = { ...RECORD, frame: "" };
  await expect(writeRecordedFrame(out, blank)).rejects.toThrow(/incomplete recorded frame/);
  // The refusal is before the write: no half-record is left behind.
  await expect(stat(out)).rejects.toThrow();
});

test("the committed fixtures still parse and re-serialize byte for byte", async () => {
  let checked = 0;
  for (const url of FIXTURES) {
    const text = await readFile(url, "utf8");
    const parsed: unknown = JSON.parse(text);
    expect(isRecordedFrame(parsed), `${url.pathname} no longer parses`).toBe(true);
    expect(serializeRecordedFrame(parsed as RecordedFrame)).toBe(text);
    checked += 1;
  }
  expect(checked).toBe(FIXTURES.length);
});
