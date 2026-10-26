/**
 * CLI: record the digichat TUI's chat pane and write it as JSON.
 *
 * Usage:
 *   bun src/export-frame.ts [--out <file>] [--width <cols>] [--height <rows>]
 *                           [--captured-at <ISO-with-zone>]
 *
 * The written record is what the dashboard renders (ADR D7). The default
 * output lives with the client; the dashboard fixture copy is written by the
 * dashboard slice that mounts it (DIG-5204).
 *
 * `--captured-at` pins the one field that would otherwise move between two
 * captures, so a committed fixture reproduces byte for byte.
 */
import { resolve } from "node:path";

import { parseFlags, positiveInt, zonedIso } from "../../../packages/tui-frame/src/flags.ts";
import { writeRecordedFrame } from "../../../packages/tui-frame/src/write.ts";

const HERE = import.meta.dir;

export const DEFAULT_OUT = resolve(HERE, "../fixtures/digichat-tui.json");

export type ExportArgs = {
  out: string;
  width?: number;
  height?: number;
  capturedAt?: string;
};

const FLAGS = ["--out", "--width", "--height", "--captured-at"] as const;

/** Parse the CLI arguments. Unknown flags and stray words are refused. */
export function parseArgs(argv: string[]): ExportArgs {
  const flags = parseFlags(argv, FLAGS);
  const args: ExportArgs = {
    out: resolve(flags.get("--out") ?? DEFAULT_OUT),
  };
  const width = flags.get("--width");
  if (width !== undefined) args.width = positiveInt(width, "--width");
  const height = flags.get("--height");
  if (height !== undefined) args.height = positiveInt(height, "--height");
  const capturedAt = flags.get("--captured-at");
  if (capturedAt !== undefined) args.capturedAt = zonedIso(capturedAt, "--captured-at");
  return args;
}

export const USAGE = [
  "Usage: bun src/export-frame.ts [--out <file>] [--width <cols>] [--height <rows>]",
  "                                  [--captured-at <ISO-with-zone>]",
  "",
  "Records the digichat chat pane with the OpenTUI captureCharFrame() harness",
  "and writes it as JSON for the dashboard preview (DIG-2698, ADR D7).",
].join("\n");

async function main(): Promise<void> {
  const argv = process.argv.slice(2);
  if (argv.includes("--help") || argv.includes("-h")) {
    console.log(USAGE);
    return;
  }
  let args: ExportArgs;
  try {
    args = parseArgs(argv);
  } catch (error) {
    console.error(error instanceof Error ? error.message : String(error));
    console.error(USAGE);
    process.exit(1);
  }
  const { captureChatThread } = await import("./capture");
  const record = await captureChatThread({
    width: args.width,
    height: args.height,
    capturedAt: args.capturedAt,
  });
  await writeRecordedFrame(args.out, record);
  console.log(`wrote ${args.out} (${record.width}x${record.height})`);
}

if (import.meta.main) {
  await main();
}