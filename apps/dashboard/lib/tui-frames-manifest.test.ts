/**
 * Contract for the committed recorded TUI frames (DIG-2698, D9).
 *
 * The frames under `fixtures/tui-frames/` are committed artifacts: the exporter
 * writes them, the dashboard renders them. This test keeps the directory and
 * the manifest in step, so a hand-edited frame, a deleted screenshot or an
 * orphan file turns the suite red instead of shipping quietly.
 *
 * The frames themselves are validated against the exporter in
 * `clients/digiquant-tui/src/export-frame.test.ts`, which re-renders the desk
 * and compares the result with the committed file.
 */

import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

import { isRecordedTuiFrame } from './tui-preview';

const PNG_MAGIC = Buffer.from([0x89, 0x50, 0x4e, 0x47]);

const LIB_DIR = dirname(fileURLToPath(import.meta.url));
const FIXTURES_DIR = join(LIB_DIR, '../fixtures/tui-frames');
const MANIFEST_PATH = join(FIXTURES_DIR, 'manifest.json');

type FrameEntry = { source: string; path: string; file: string; exporter: string };
type ScreenshotEntry = { source: string; viewport: string; file: string };
type Manifest = { version: number; frames: FrameEntry[]; screenshots: ScreenshotEntry[] };

function loadManifest(): Manifest {
  return JSON.parse(readFileSync(MANIFEST_PATH, 'utf8')) as Manifest;
}

describe('recorded TUI frame fixtures', () => {
  it('lists every committed frame and every screenshot, and nothing else', () => {
    const manifest = loadManifest();
    expect(manifest.version).toBe(1);

    const frameFiles = readdirSync(FIXTURES_DIR)
      .filter((name) => name.endsWith('.json') && name !== 'manifest.json')
      .sort();
    const listedFrames = manifest.frames.map((entry) => entry.file).sort();
    expect(listedFrames).toEqual(frameFiles);

    const screenshotFiles = readdirSync(join(FIXTURES_DIR, 'screenshots')).sort();
    const listedScreenshots = manifest.screenshots.map((entry) => entry.file).sort();
    expect(listedScreenshots).toEqual(
      screenshotFiles.map((file) => `screenshots/${file}`),
    );
  });

  it('holds every listed frame as a valid recorded frame', () => {
    const manifest = loadManifest();
    expect(manifest.frames.length).toBeGreaterThan(0);
    for (const entry of manifest.frames) {
      const raw = JSON.parse(readFileSync(join(FIXTURES_DIR, entry.file), 'utf8'));
      expect(isRecordedTuiFrame(raw), `${entry.file} is not a recorded frame`).toBe(true);
      expect(raw.source).toBe(entry.source);
      expect(raw.path).toBe(entry.path);
      expect(entry.exporter).not.toBe('');
    }
  });

  it('keeps every listed screenshot on disk as a real PNG', () => {
    const manifest = loadManifest();
    expect(manifest.screenshots.length).toBeGreaterThan(0);
    for (const entry of manifest.screenshots) {
      const abs = join(FIXTURES_DIR, entry.file);
      expect(existsSync(abs), `${entry.file} is missing`).toBe(true);
      expect(statSync(abs).size).toBeGreaterThan(0);
      const head = readFileSync(abs).subarray(0, 4);
      expect(head.equals(PNG_MAGIC), `${entry.file} is not a PNG`).toBe(true);
    }
  });
});
