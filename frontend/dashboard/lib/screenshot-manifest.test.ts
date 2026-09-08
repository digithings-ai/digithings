import { describe, expect, it } from 'vitest';

import { PIPELINE_TOPOLOGY } from './pipeline-topology';
import {
  REQUIRED_ARTIFACT_FAMILY_IDS,
  artifactFamiliesMissingFromManifest,
  invalidPngScreenshotPaths,
  loadScreenshotManifest,
  missingScreenshotPaths,
  requiredScreenshotPaths,
  stagesMissingFromManifest,
} from './screenshot-manifest';

describe('screenshot fixture gate (#2645)', () => {
  const manifest = loadScreenshotManifest();

  it('covers every PIPELINE_TOPOLOGY stage with desktop + mobile paths', () => {
    expect(stagesMissingFromManifest(manifest)).toEqual([]);
    expect(manifest.stages.map((s) => s.stageId).sort()).toEqual(
      PIPELINE_TOPOLOGY.map((s) => s.id).sort(),
    );
    for (const stage of manifest.stages) {
      expect(stage.desktop).toMatch(new RegExp(`^stages/${stage.stageId}-desktop\\.png$`));
      expect(stage.mobile).toMatch(new RegExp(`^stages/${stage.stageId}-mobile\\.png$`));
    }
  });

  it('lists every required representative artifact family', () => {
    expect(artifactFamiliesMissingFromManifest(manifest)).toEqual([]);
    expect(manifest.artifactFamilies.map((f) => f.id).sort()).toEqual(
      [...REQUIRED_ARTIFACT_FAMILY_IDS].sort(),
    );
  });

  it('fails when a required screenshot path is missing from fixtures/', () => {
    const missing = missingScreenshotPaths(manifest);
    expect(missing, `missing fixtures:\n${missing.join('\n')}`).toEqual([]);
  });

  it('requires committed fixtures to be PNG files', () => {
    const invalid = invalidPngScreenshotPaths(manifest);
    expect(invalid, `non-PNG fixtures:\n${invalid.join('\n')}`).toEqual([]);
  });

  it('exposes a stable required-path inventory for docs parity', () => {
    const paths = requiredScreenshotPaths(manifest);
    // 6 stages × 2 viewports + 12 artifact families
    expect(paths).toHaveLength(24);
    expect(new Set(paths).size).toBe(paths.length);
  });
});
