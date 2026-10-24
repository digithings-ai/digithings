import { describe, expect, test } from "bun:test";
import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { captureDeskPane } from "./capture";
import { parseArgs } from "./export-frame";

const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../../..");
const ARTIFACT = resolve(REPO_ROOT, "apps/dashboard/fixtures/tui-frames/digiquant-tui.json");

/** The capture date is the only thing that moves between two captures. */
function normalize(frame: string): string {
  return frame.replace(/\d{4}-\d{2}-\d{2}/g, "<date>");
}

describe("the exporter command line", () => {
  test("it refuses an unknown flag instead of ignoring it", () => {
    expect(() => parseArgs(["--width", "80"])).toThrow(/unknown flag/);
  });

  test("it takes --path=/x as well as --path /x", () => {
    expect(parseArgs(["--path=/portfolio"]).path).toBe("/portfolio");
  });

  test("it refuses a flag with no value", () => {
    expect(() => parseArgs(["--path"])).toThrow(/needs a value/);
    expect(() => parseArgs(["--path", "--out"])).toThrow(/needs a value/);
  });

  test("it refuses a stray argument", () => {
    expect(() => parseArgs(["/brief"])).toThrow(/unexpected argument/);
  });

  test("it reads and pins the capture time", () => {
    expect(parseArgs(["--captured-at", "2026-10-22T09:00:00.000Z"]).capturedAt).toBe(
      "2026-10-22T09:00:00.000Z",
    );
    expect(parseArgs(["--captured-at=2026-10-22T09:00:00.000Z"]).capturedAt).toBe(
      "2026-10-22T09:00:00.000Z",
    );
    // An offset-less time would label a different moment on another machine.
    expect(() => parseArgs(["--captured-at", "2026-10-22T09:00:00"])).toThrow(/zone/);
  });
});

describe("the committed recorded frame", () => {
  test("the shipped artifact is what the exporter writes today", async () => {
    // The artifact is committed, so it can be checked against the exporter that
    // wrote it: a hand-edited frame, a crop that drifted, or a changed title
    // all fail here.
    const committed = JSON.parse(await readFile(ARTIFACT, "utf8"));
    const record = await captureDeskPane({
      path: committed.path,
      capturedAt: committed.capturedAt,
    });
    expect(record.source).toBe(committed.source);
    expect(record.path).toBe(committed.path);
    expect(record.width).toBe(committed.width);
    expect(record.height).toBe(committed.height);
    expect(normalize(record.frame)).toBe(normalize(committed.frame));
  }, 60000);
});
