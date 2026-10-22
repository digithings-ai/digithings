/**
 * Writes a recorded digiquant TUI frame for the dashboard (D9, DIG-2698).
 *
 * Usage:
 *   bun src/export-frame.ts                       # records /brief
 *   bun src/export-frame.ts --path /portfolio     # records another desk page
 *   bun src/export-frame.ts --out <file>          # writes elsewhere
 *   bun src/export-frame.ts --help
 *
 * The record is JSON: the source, the path, the capture time, the size and
 * the frame itself. The dashboard reads it and renders the frame as text in
 * Geist Mono. No live socket, no CSP change (ADR D7).
 *
 * The capture reads the desk through the fixture API, so the frame is
 * reproducible and carries no live book: a shipped artifact must not commit
 * positions. Unknown flags are refused rather than ignored, so a mistyped
 * option cannot silently write a different record.
 */

import { mkdir, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { captureDeskPane, DEFAULT_DESK_PATH } from './capture';
import { serializeRecordedFrame } from './frame';

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(HERE, '../../..');
const DEFAULT_OUT = resolve(REPO_ROOT, 'apps/dashboard/fixtures/tui-frames/digiquant-tui.json');

const USAGE = `Usage:
  bun src/export-frame.ts [--path /brief] [--out <file>]
  bun src/export-frame.ts --help

Records the main desk pane of the digiquant TUI and writes it as JSON for the
dashboard's recorded-frame preview (D9, DIG-2698). The capture reads the desk
through the fixture API, so the frame is reproducible and carries no live book.
`;

const FLAGS = ['--path', '--out'] as const;

/** Parse the command line strictly: an unknown flag is an error, not a shrug. */
export function parseArgs(argv: string[]): { path: string; out: string } {
  const values = new Map<string, string>();
  for (let index = 0; index < argv.length; index += 1) {
    const entry = argv[index];
    if (!entry.startsWith('--')) {
      throw new Error(`unexpected argument "${entry}"\n${USAGE}`);
    }
    const equals = entry.indexOf('=');
    const name = equals === -1 ? entry : entry.slice(0, equals);
    if (!FLAGS.includes(name as (typeof FLAGS)[number])) {
      throw new Error(`unknown flag "${name}"\n${USAGE}`);
    }
    let value: string | undefined;
    if (equals === -1) {
      value = argv[index + 1];
      index += 1;
    } else {
      value = entry.slice(equals + 1);
    }
    if (!value || value.startsWith('--')) {
      throw new Error(`${name} needs a value\n${USAGE}`);
    }
    values.set(name, value);
  }
  return {
    path: values.get('--path') ?? DEFAULT_DESK_PATH,
    out: resolve(values.get('--out') ?? DEFAULT_OUT),
  };
}

if (import.meta.main) {
  if (process.argv.includes('--help')) {
    console.log(USAGE);
  } else {
    try {
      const { path, out } = parseArgs(process.argv.slice(2));
      const record = await captureDeskPane({ path });
      await mkdir(dirname(out), { recursive: true });
      await writeFile(out, serializeRecordedFrame(record), 'utf8');
      console.log(
        `wrote ${out}\n  source ${record.source} · ${record.path} · ${record.width}x${record.height} · ${record.capturedAt}`,
      );
    } catch (error) {
      console.error(error instanceof Error ? error.message : String(error));
      process.exit(1);
    }
  }
}
