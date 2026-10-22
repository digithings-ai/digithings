import { expect, test } from "bun:test";
import { mkdtemp, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { DEFAULT_OUT, parseArgs } from "./export-frame";

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

test("the CLI refuses an unknown flag, a missing value and a stray word", () => {
  expect(() => parseArgs(["--nope"])).toThrow(/unknown flag/);
  expect(() => parseArgs(["--out"])).toThrow(/needs a value/);
  expect(() => parseArgs(["--width"])).toThrow(/needs a value/);
  expect(() => parseArgs(["--width", "0"])).toThrow(/positive whole number/);
  expect(() => parseArgs(["--width", "wide"])).toThrow(/positive whole number/);
  expect(() => parseArgs(["--width", "80px"])).toThrow(/positive whole number/);
  expect(() => parseArgs(["--width", "12.9"])).toThrow(/positive whole number/);
  expect(() => parseArgs(["extra"])).toThrow(/unknown flag/);
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
  expect(stdout).toContain("wrote");
  expect(stderr).not.toContain("the digichat thread did not load");

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

  // The frame carries the fixture's own conversation, so it was recorded
  // from the fixture and not from a live backend.
  expect(record.frame).toContain("what is a recorded frame");
  expect(record.frame).toContain("a recorded captureCharFrame() frame");
  expect(record.frame).toContain("Ask digichat");
  expect(record.frame).not.toContain("the official API could not be reached");

  // The rail is cropped away: the session title lives only in the rail, and
  // every thread row starts in the pane's own padding, so no rail border is
  // left in the frame.
  expect(record.frame).not.toContain("book");
  for (const row of record.frame.split("\n")) {
    if (row.trim() === "") continue;
    expect(row.startsWith("  ")).toBe(true);
  }

  expect(record.width).toBeGreaterThan(0);
  expect(record.height).toBe(record.frame.split("\n").length);
  expect(record.width).toBe(
    Math.max(...record.frame.split("\n").map((row) => row.length)),
  );
});
