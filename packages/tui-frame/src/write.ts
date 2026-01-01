/**
 * The exporter write path (DIG-2698, ADR D7).
 *
 * Both TUI exporters end the same way: make the output directory, serialize
 * the record, write it. They had a copy each — one through `Bun.write`, one
 * through `node:fs` — and neither checked the record before writing, so a
 * capture that lost its frame wrote a file the dashboard's guard then dropped:
 * the preview vanished with nothing failing.
 *
 * Deliberately not re-exported from `index.ts`. The dashboard imports this
 * package in the browser, and a `node:fs` specifier must not enter that bundle.
 * The exporters deep-import this module, the way they already import
 * `record.ts`.
 */

import { mkdir, writeFile } from "node:fs/promises";
import { dirname } from "node:path";

import {
  isRecordedFrame,
  serializeRecordedFrame,
  type RecordedFrame,
} from "./record";

/**
 * Write one record as the committed JSON fixture, creating parent directories.
 * Refuses a record the dashboard would reject, so an incomplete capture fails
 * here — where the exporter can report it — instead of silently disappearing
 * from the preview.
 */
export async function writeRecordedFrame(
  out: string,
  record: RecordedFrame,
): Promise<string> {
  if (!isRecordedFrame(record)) {
    throw new Error(`refusing to write an incomplete recorded frame to ${out}`);
  }
  await mkdir(dirname(out), { recursive: true });
  await writeFile(out, serializeRecordedFrame(record), "utf8");
  return out;
}
