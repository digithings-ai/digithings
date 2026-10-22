/**
 * Contract for the committed D8 preview screenshots (DIG-5138).
 *
 * The PNGs under `fixtures/digichat-live-preview/` are committed evidence:
 * they are what a reviewer looks at to judge the layout without a running
 * dashboard. This test keeps the directory and the manifest in step, so a
 * deleted screenshot or an orphan file turns the suite red instead of
 * shipping quietly.
 *
 * The layout itself is pinned by `components/app-frame-preview-layout.test.tsx`
 * (the preview lives inside the content column) and by
 * `components/digichat-live-preview.test.tsx` (the strip is `w-full`, the
 * embed is explicitly sized, the strip ships collapsed).
 */

import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it } from 'vitest';

const PNG_MAGIC = Buffer.from([0x89, 0x50, 0x4e, 0x47]);

const LIB_DIR = dirname(fileURLToPath(import.meta.url));
const FIXTURES_DIR = join(LIB_DIR, '../fixtures/digichat-live-preview');
const MANIFEST_PATH = join(FIXTURES_DIR, 'manifest.json');

type ScreenshotEntry = { surface: string; viewport: string; file: string };
type Manifest = { version: number; screenshots: ScreenshotEntry[] };

function loadManifest(): Manifest {
  return JSON.parse(readFileSync(MANIFEST_PATH, 'utf8')) as Manifest;
}

describe('digichat live preview fixtures', () => {
  it('lists every committed screenshot, and nothing else', () => {
    const manifest = loadManifest();
    expect(manifest.version).toBe(1);

    const screenshotFiles = readdirSync(join(FIXTURES_DIR, 'screenshots')).sort();
    const listedScreenshots = manifest.screenshots.map((entry) => entry.file).sort();
    expect(listedScreenshots).toEqual(
      screenshotFiles.map((file) => `screenshots/${file}`),
    );
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

  it('keeps a desktop and a phone shot of the surface', () => {
    const viewports = loadManifest().screenshots.map((entry) => entry.viewport);
    expect(viewports).toContain('desktop-collapsed');
    expect(viewports).toContain('phone-open');
  });
});
