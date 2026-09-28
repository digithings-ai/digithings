/**
 * Pipeline glass-box screenshot fixture contract (#2645 / #1945).
 *
 * Manifest + on-disk PNG paths are the mergeable automated slice; operator
 * capture may replace 1×1 placeholders without changing the path contract.
 */

import { existsSync, readFileSync, statSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { PIPELINE_TOPOLOGY, type PipelineStageId } from './pipeline-topology';

export type ScreenshotViewport = 'desktop' | 'mobile';

export interface ScreenshotStageEntry {
  stageId: PipelineStageId;
  desktop: string;
  mobile: string;
}

export interface ScreenshotArtifactFamily {
  id: string;
  label: string;
  path: string;
  exampleDocumentKey: string | null;
}

export interface ScreenshotManifest {
  version: number;
  description?: string;
  stages: ScreenshotStageEntry[];
  artifactFamilies: ScreenshotArtifactFamily[];
}

const PNG_MAGIC = Buffer.from([0x89, 0x50, 0x4e, 0x47]);

const LIB_DIR = dirname(fileURLToPath(import.meta.url));
export const SCREENSHOT_FIXTURES_DIR = join(LIB_DIR, '../fixtures/screenshots');
export const SCREENSHOT_MANIFEST_PATH = join(SCREENSHOT_FIXTURES_DIR, 'manifest.json');

/** Families that must appear in the manifest (stable ids for the Vitest gate). */
export const REQUIRED_ARTIFACT_FAMILY_IDS: readonly string[] = [
  'attention-plan',
  'research-segment',
  'fanout-alt-data',
  'fanout-analyst',
  'digest',
  'deliberation',
  'pm-direction',
  'pm-rebalance',
  'commit',
  'beliefs',
  'call-trace',
  'artifact-ledger',
] as const;

export function loadScreenshotManifest(
  manifestPath: string = SCREENSHOT_MANIFEST_PATH,
): ScreenshotManifest {
  const raw = JSON.parse(readFileSync(manifestPath, 'utf8')) as ScreenshotManifest;
  if (!raw || typeof raw !== 'object') {
    throw new Error('screenshot manifest must be a JSON object');
  }
  if (!Array.isArray(raw.stages) || !Array.isArray(raw.artifactFamilies)) {
    throw new Error('screenshot manifest requires stages[] and artifactFamilies[]');
  }
  return raw;
}

/** Relative paths every stage × viewport + artifact family must provide. */
export function requiredScreenshotPaths(manifest: ScreenshotManifest): string[] {
  const paths: string[] = [];
  for (const stage of manifest.stages) {
    paths.push(stage.desktop, stage.mobile);
  }
  for (const family of manifest.artifactFamilies) {
    paths.push(family.path);
  }
  return paths;
}

export function missingScreenshotPaths(
  manifest: ScreenshotManifest,
  fixturesDir: string = SCREENSHOT_FIXTURES_DIR,
): string[] {
  return requiredScreenshotPaths(manifest).filter((rel) => {
    const abs = join(fixturesDir, rel);
    return !existsSync(abs) || statSync(abs).size === 0;
  });
}

/** Paths that exist but are not valid PNG files (wrong type / truncated). */
export function invalidPngScreenshotPaths(
  manifest: ScreenshotManifest,
  fixturesDir: string = SCREENSHOT_FIXTURES_DIR,
): string[] {
  const bad: string[] = [];
  for (const rel of requiredScreenshotPaths(manifest)) {
    const abs = join(fixturesDir, rel);
    if (!existsSync(abs) || statSync(abs).size === 0) continue;
    const head = readFileSync(abs).subarray(0, 4);
    if (!head.equals(PNG_MAGIC)) bad.push(rel);
  }
  return bad;
}

/** Topology stage ids that lack a desktop+mobile manifest entry. */
export function stagesMissingFromManifest(manifest: ScreenshotManifest): PipelineStageId[] {
  const covered = new Set(manifest.stages.map((s) => s.stageId));
  return PIPELINE_TOPOLOGY.map((s) => s.id).filter((id) => !covered.has(id));
}

/** Required artifact family ids absent from the manifest. */
export function artifactFamiliesMissingFromManifest(manifest: ScreenshotManifest): string[] {
  const present = new Set(manifest.artifactFamilies.map((f) => f.id));
  return REQUIRED_ARTIFACT_FAMILY_IDS.filter((id) => !present.has(id));
}
