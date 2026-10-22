/**
 * CLI: record the digichat TUI's chat pane and write it as JSON.
 *
 * Usage:
 *   bun src/export-frame.ts [--out <file>] [--width <cols>] [--height <rows>]
 *
 * The written record is what the dashboard renders (ADR D7). The default
 * output lives with the client; the dashboard fixture copy is written by the
 * dashboard slice that mounts it.
 */
import { mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";

import { serializeRecordedFrame } from "./frame";

const HERE = import.meta.dir;

export const DEFAULT_OUT = resolve(HERE, "../fixtures/digichat-tui.json");

export type ExportArgs = {
  out: string;
  width?: number;
  height?: number;
};

function positiveInt(value: string, flag: string): number {
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed <= 0) {
    throw new Error(`${flag} needs a positive whole number, got "${value}"`);
  }
  return parsed;
}

/** Parse the CLI arguments. Unknown flags and stray words are refused. */
export function parseArgs(argv: string[]): ExportArgs {
  const args: ExportArgs = { out: DEFAULT_OUT };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    const [flag, inline] = arg.startsWith("--") && arg.includes("=")
      ? [arg.slice(0, arg.indexOf("=")), arg.slice(arg.indexOf("=") + 1)]
      : [arg, undefined];
    const value = () => {
      if (inline !== undefined) return inline;
      const next = argv[index + 1];
      if (next === undefined || next.startsWith("--")) {
        throw new Error(`${flag} needs a value`);
      }
      index += 1;
      return next;
    };
    switch (flag) {
      case "--out":
        args.out = resolve(value());
        break;
      case "--width":
        args.width = positiveInt(value(), flag);
        break;
      case "--height":
        args.height = positiveInt(value(), flag);
        break;
      default:
        throw new Error(`unknown flag ${arg}`);
    }
  }
  return args;
}

export const USAGE = [
  "Usage: bun src/export-frame.ts [--out <file>] [--width <cols>] [--height <rows>]",
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
  });
  await mkdir(dirname(args.out), { recursive: true });
  await Bun.write(args.out, serializeRecordedFrame(record));
  console.log(`wrote ${args.out} (${record.width}x${record.height})`);
}

if (import.meta.main) {
  await main();
}
