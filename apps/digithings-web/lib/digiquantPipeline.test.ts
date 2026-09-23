import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { PIPELINE_PHASES, PORTFOLIO_PHASES, RESEARCH_PHASES } from "./digiquantPipeline";

/**
 * The landing band's phase lists are a copy of the digiquant site's, because the
 * two live in separate Next app roots and neither can import the other's `@/app`
 * module. A copy that can silently drift is worse than no copy, so this test
 * reads the original from disk and compares.
 *
 * If it fails, the fix is to copy the change across — not to relax the test. The
 * digiquant original is itself pinned to the real graph by its own
 * `pipeline-data.test.ts`, so this chain ends at the code that runs.
 */

const ORIGINAL = resolve(
  __dirname,
  "..",
  "..",
  "digiquant-web",
  "app",
  "_pipeline.ts",
);

type Phase = { id: string; name: string; detail: string };

function extract(source: string, exportName: string): Phase[] {
  const start = source.indexOf(`export const ${exportName}`);
  expect(start, `${exportName} not found in the digiquant original`).toBeGreaterThan(-1);
  const end = source.indexOf("];", start);
  const block = source.slice(start, end);
  const pattern = /\{\s*id:\s*"([^"]+)",\s*name:\s*"([^"]+)",\s*detail:\s*"([^"]+)"\s*\}/g;
  const out: Phase[] = [];
  for (const match of block.matchAll(pattern)) {
    out.push({ id: match[1], name: match[2], detail: match[3] });
  }
  return out;
}

describe("digiquantPipeline", () => {
  const source = readFileSync(ORIGINAL, "utf8");

  it("matches the research phases in the digiquant original", () => {
    expect(RESEARCH_PHASES).toEqual(extract(source, "RESEARCH_PHASES"));
  });

  it("matches the portfolio phases in the digiquant original", () => {
    expect(PORTFOLIO_PHASES).toEqual(extract(source, "PORTFOLIO_PHASES"));
  });

  it("counts only phases that ship", () => {
    expect(PIPELINE_PHASES).toHaveLength(RESEARCH_PHASES.length + PORTFOLIO_PHASES.length);
    expect(PIPELINE_PHASES).toHaveLength(20);
  });

  it("leaves execution without phases", () => {
    const execution = extract(source, "PIPELINE_ENGINES");
    expect(execution.some((p) => p.name === "")).toBe(false);
    expect(PIPELINE_PHASES.map((p) => p.id)).not.toContain("execution");
  });
});
