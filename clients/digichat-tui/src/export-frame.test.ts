import { expect, test } from "bun:test";
import { mkdtemp, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";

import { captureChatThread } from "./capture";
import { DEFAULT_OUT, parseArgs } from "./export-frame";

const ARTIFACT = resolve(dirname(import.meta.dir), "fixtures/digichat-tui.json");

test("the CLI defaults to the client fixture path", () => {
  const args = parseArgs([]);
  expect(args.out).toBe(DEFAULT_OUT);
  expect(args.out.endsWith("/clients/digichat-tui/fixtures/digichat-tui.json")).toBe(true);
});

test("the CLI reads the output path in both spellings", () => {
  expect(parseArgs(["--out", "/tmp/frame.json"]).out).toBe("/tmp/frame.json");
  expect(parseArgs(["--out=/tmp/frame.json"]).out).toBe("/tmp/frame.json");
});

test("the CLI reads the capture size", () => {
  const args = parseArgs(["--width", "120", "--height", "50"]);
  expect(args.width).toBe(120);
  expect(args.height).toBe(50);
});

test("the CLI reads a pinned capture time", () => {
  expect(parseArgs(["--captured-at", "2026-10-22T05:45:00.868Z"]).capturedAt).toBe(
    "2026-10-22T05:45:00.868Z",
  );
  expect(parseArgs(["--captured-at=2026-10-22T05:45:00.868Z"]).capturedAt).toBe(
    "2026-10-22T05:45:00.868Z",
  );
});

test("the CLI refuses an unknown flag, a missing value and a stray word", () => {
  expect(() => parseArgs(["--nope"])).toThrow(/unknown flag/);
  expect(() => parseArgs(["--out"])).toThrow(/needs a value/);
  expect(() => parseArgs(["--width"])).toThrow(/needs a value/);
  expect(() => parseArgs(["--width", "0"])).toThrow(/positive number/);
  expect(() => parseArgs(["--width", "wide"])).toThrow(/positive number/);
  expect(() => parseArgs(["--captured-at", "yesterday"])).toThrow(/zone/);
  expect(() => parseArgs(["extra"])).toThrow(/unexpected argument/);
});

test("the CLI records the chat pane of the real client", async () => {
  // The CLI runs in its own process: the client resolves its API base when
  // its module loads, so the exporter must control the environment before
  // that happens. The record it writes is what the dashboard renders.
  const dir = await mkdtemp(join(tmpdir(), "digichat-tui-frame-"));
  const out = join(dir, "frame.json");
  const child = Bun.spawn(["bun", "src/export-frame.ts", "--out", out], {
    stdout: "pipe",
    stderr: "pipe",
  });
  const [stdout, stderr, exitCode] = await Promise.all([
    new Response(child.stdout).text(),
    new Response(child.stderr).text(),
    child.exited,
  ]);
  expect(exitCode).toBe(0);
  expect(stderr).not.toContain("error:");
  expect(stdout).toContain("wrote");

  const record = JSON.parse(await readFile(out, "utf8")) as {
    source: string;
    path: string;
    capturedAt: string;
    width: number;
    height: number;
    frame: string;
  };
  expect(record.source).toBe("digichat-tui");
  expect(record.path).toBe("/thread");
  expect(record.capturedAt.length).toBeGreaterThan(0);
  expect(record.frame).toContain("captureCharFrame");
  expect(record.frame).not.toContain("the official API could not be reached");
  // The rail is cropped away: the session title lives only in the rail.
  expect(record.frame).not.toContain("book");
  expect(record.width).toBeLessThan(100);
  expect(record.height).toBeGreaterThan(0);
});

test("the committed fixture is what the exporter writes today", async () => {
  // The artifact is committed, so the exporter can be checked against it: a
  // hand-edited frame, a crop that drifted or a changed fixture all fail here.
  // The capture time is pinned from the artifact, so the comparison holds.
  const committed = JSON.parse(await readFile(ARTIFACT, "utf8"));
  const record = await captureChatThread({ capturedAt: committed.capturedAt });
  expect(record).toEqual(committed);
});
