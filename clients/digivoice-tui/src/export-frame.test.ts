import { expect, test } from "bun:test";
import { mkdtemp, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";

import { captureSetupPane, waitForSetupFrame } from "./capture";
import { DEFAULT_OUT, parseArgs } from "./export-frame";

const ARTIFACT = resolve(dirname(import.meta.dir), "fixtures/digivoice-tui.json");

test("the CLI defaults to the client fixture path", () => {
  const args = parseArgs([]);
  expect(args.out).toBe(DEFAULT_OUT);
  expect(args.out.endsWith("/clients/digivoice-tui/fixtures/digivoice-tui.json")).toBe(true);
});

test("the CLI reads the output path in both spellings", () => {
  expect(parseArgs(["--out", "/tmp/frame.json"]).out).toBe("/tmp/frame.json");
  expect(parseArgs(["--out=/tmp/frame.json"]).out).toBe("/tmp/frame.json");
});

test("the CLI reads the capture size", () => {
  const args = parseArgs(["--width", "120", "--height", "40"]);
  expect(args.width).toBe(120);
  expect(args.height).toBe(40);
});

test("the CLI reads a pinned capture time", () => {
  expect(parseArgs(["--captured-at", "2026-10-25T02:33:52.470Z"]).capturedAt).toBe(
    "2026-10-25T02:33:52.470Z",
  );
  expect(parseArgs(["--captured-at=2026-10-25T02:33:52.470Z"]).capturedAt).toBe(
    "2026-10-25T02:33:52.470Z",
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

test(
  "the CLI records the setup pane of the real client",
  async () => {
    // The CLI runs in its own process: the client resolves its CLI prefix when
    // its module loads, so the exporter must control the environment before
    // that happens. The record it writes is what the dashboard renders.
    const dir = await mkdtemp(join(tmpdir(), "digivoice-tui-frame-"));
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
    // The child's own output is the only way to see why it failed, so it is in
    // the message rather than a bare exit code.
    if (exitCode !== 0) {
      throw new Error(`the exporter exited ${exitCode}\nstdout:\n${stdout}\nstderr:\n${stderr}`);
    }
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
    expect(record.source).toBe("digivoice-tui");
    expect(record.path).toBe("/setup");
    expect(record.capturedAt.length).toBeGreaterThan(0);
    expect(record.frame).toContain("DigiVoice");
    expect(record.frame).toContain("Live status");
    expect(record.frame).not.toContain("not reachable");
    // The rail is cropped away: the setup menu lives only in the rail.
    expect(record.frame).not.toContain("Models (STT / TTS");
    expect(record.width).toBeLessThan(100);
    expect(record.height).toBeGreaterThan(0);
  },
  // A cold `bun` child under the local-ci pool is routinely slower than bun's
  // 5 s default, and a timeout there is a flake, not a finding.
  60_000,
);

test("the wait polls until the CLI answers instead of recording the error screen", async () => {
  // The app paints "not reachable" until its first read lands. A fixed settle
  // wait recorded that error screen in the local-ci pool, where six steps share
  // the host; this pins the poll.
  const frames = [
    "digivoice CLI not reachable\ndata: —",
    "digivoice CLI not reachable\ndata: —",
    "DigiVoice · local speech config\ndata: /tmp/digivoice",
  ];
  let passes = 0;
  const frame = await waitForSetupFrame(
    {
      capture: () => frames[Math.min(passes, frames.length - 1)],
      refresh: async () => {
        passes += 1;
      },
    },
    { attempts: 5, delayMs: 1 },
  );
  expect(frame).toContain("/tmp/digivoice");
  expect(passes).toBe(2);
});

test("the wait fails when the CLI never answers", async () => {
  await expect(
    waitForSetupFrame(
      { capture: () => "digivoice CLI not reachable", refresh: async () => {} },
      { attempts: 3, delayMs: 1 },
    ),
  ).rejects.toThrow(/3 settle passes/);
});

test("the committed fixture is what the exporter writes today", async () => {
  // The artifact is committed, so the exporter can be checked against it: a
  // hand-edited frame, a crop that drifted or a changed fixture all fail here.
  // The capture time is pinned from the artifact, so the comparison holds.
  const committed = JSON.parse(await readFile(ARTIFACT, "utf8"));
  const record = await captureSetupPane({ capturedAt: committed.capturedAt });
  expect(record).toEqual(committed);
});
