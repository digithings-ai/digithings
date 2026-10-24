/**
 * Writes a recorded digiquant TUI frame for the dashboard (D9, DIG-2698).
 *
 * Usage:
 *   bun src/export-frame.ts                       # records /brief
 *   bun src/export-frame.ts --path /portfolio     # records another desk page
 *   bun src/export-frame.ts --out <file>          # writes elsewhere
 *   bun src/export-frame.ts --captured-at <ISO>   # pins the capture time
 *   bun src/export-frame.ts --help
 *
 * The record is JSON: the source, the path, the capture time, the size and
 * the frame itself. The dashboard reads it and renders the frame as text in
 * Geist Mono. No live socket, no CSP change (ADR D7).
 *
 * The capture reads the desk through the fixture API, so the frame is
 * reproducible and carries no live book: a shipped artifact must not commit
 * positions. Unknown flags are refused rather than ignored, so a mistyped
 * option cannot silently write a different record. `--captured-at` pins the
 * one field that would otherwise move between two captures, so the committed
 * fixture reproduces byte for byte.
 */

import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseFlags, zonedIso } from '../../../packages/tui-frame/src/flags.ts';
import { writeRecordedFrame } from '../../../packages/tui-frame/src/write.ts';
import { captureDeskPane, DEFAULT_DESK_PATH } from './capture';

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(HERE, '../../..');
const DEFAULT_OUT = resolve(REPO_ROOT, 'apps/dashboard/fixtures/tui-frames/digiquant-tui.json');

const USAGE = `Usage:
  bun src/export-frame.ts [--path /brief] [--out <file>] [--captured-at <ISO>]
  bun src/export-frame.ts --help

Records the main desk pane of the digiquant TUI and writes it as JSON for the
dashboard's recorded-frame preview (D9, DIG-2698). The capture reads the desk
through the fixture API, so the frame is reproducible and carries no live book.
`;

const FLAGS = ['--path', '--out', '--captured-at'] as const;

/** Parse the command line strictly: an unknown flag is an error, not a shrug. */
export function parseArgs(argv: string[]): {
  path: string;
  out: string;
  capturedAt?: string;
} {
  const flags = parseFlags(argv, FLAGS);
  const capturedAt = flags.get('--captured-at');
  return {
    path: flags.get('--path') ?? DEFAULT_DESK_PATH,
    out: resolve(flags.get('--out') ?? DEFAULT_OUT),
    ...(capturedAt === undefined
      ? {}
      : { capturedAt: zonedIso(capturedAt, '--captured-at') }),
  };
}

if (import.meta.main) {
  if (process.argv.includes('--help')) {
    console.log(USAGE);
  } else {
    try {
      const { path, out, capturedAt } = parseArgs(process.argv.slice(2));
      const record = await captureDeskPane({ path, capturedAt });
      await writeRecordedFrame(out, record);
      console.log(
        `wrote ${out}\n  source ${record.source} · ${record.path} · ${record.width}x${record.height} · ${record.capturedAt}`,
      );
    } catch (error) {
      console.error(error instanceof Error ? error.message : String(error));
      process.exit(1);
    }
  }
}
