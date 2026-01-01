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
  expect(() => parseArgs(["--width", "0"])).toThrow(/positive (whole )?number/);
  expect(() => parseArgs(["--width", "wide"])).toThrow(/positive (whole )?number/);
  expect(() => parseArgs(["--width", "80px"])).toThrow(/positive (whole )?number/);
  expect(() => parseArgs(["--width", "12.9"])).toThrow(/positive (whole )?number/);
  expect(() => parseArgs(["--captured-at", "yesterday"])).toThrow(/zone/);
  expect(() => parseArgs(["extra"])).toThrow(/(unexpected argument|unknown flag)/);
});

test(
  "the CLI records the chat pane of the real client",
  async () => {
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
    // The child's own output is the only way to see why it failed, so it goes in
    // the message rather than a bare exit code.
    if (exitCode !== 0) {
      throw new Error(`the exporter exited ${exitCode}\nstdout:\n${stdout}\nstderr:\n${stderr}`);
    }
    expect(stdout).toContain("wrote");
    expect(stderr).not.toContain("error:");
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

    expect(record.frame).toContain("what is a recorded frame");
    expect(record.frame).toContain("a recorded captureCharFrame() frame");
    expect(record.frame).toContain("Ask digichat");
    expect(record.frame).not.toContain("the official API could not be reached");

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
  },
  // A cold `bun` child under the local-ci pool is routinely slower than bun's
  // 5 s default, and a timeout there is a flake, not a finding.
  60_000,
);
test("the committed fixture is what the exporter writes today", async () => {
  const committed = JSON.parse(await readFile(ARTIFACT, "utf8"));
  const record = await captureChatThread({ capturedAt: committed.capturedAt });
  expect(record).toEqual(committed);
});

test(
  "a second capture in one process still proves it read the fixture",
  async () => {
    // Two captures in one process: the guard resets the fixture counter at the
    // start of each capture, so the second frame must make its own reads. If
    // the client stopped refetching per mount, this capture would read nothing
    // and the guard would throw rather than record a stale frame.
    const first = await captureChatThread({ capturedAt: "2026-10-22T06:00:00.000Z" });
    const second = await captureChatThread({ capturedAt: "2026-10-22T06:00:00.000Z" });
    expect(second.frame).toBe(first.frame);
    expect(second.frame).toContain("what is a recorded frame");
  },
  30_000,
);
