import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { PIPELINE_ENGINES, PIPELINE_PHASES, PORTFOLIO_PHASES, RESEARCH_PHASES } from "./digiquantPipeline";

/**
 * The landing band's phase lists are a copy of digiquant's PipelineScene, because
 * the two live in separate Next app roots and neither can import the other's
 * modules. A copy that can silently drift is worse than no copy, so this test
 * reads the original from disk and compares.
 *
 * If it fails, the fix is to copy the change across — not to relax the test.
 * Source of truth: `apps/digiquant-web/components/landing/PipelineScene.tsx`
 * (`const RESEARCH` / `const PORTFOLIO` tuple lists). The Q1 `app/_pipeline.ts`
 * module no longer ships on develop.
 */

const ORIGINAL = resolve(
  __dirname,
  "..",
  "..",
  "digiquant-web",
  "components",
  "landing",
  "PipelineScene.tsx",
);

type Phase = { id: string; name: string; detail: string };

function extractTupleList(source: string, constName: string): Phase[] {
  const start = source.indexOf(`const ${constName}`);
  expect(start, `${constName} not found in PipelineScene`).toBeGreaterThan(-1);
  const end = source.indexOf("];", start);
  const block = source.slice(start, end);
  const pattern = /\["([^"]+)",\s*"([^"]+)",\s*"([^"]+)"\]/g;
  const out: Phase[] = [];
  for (const match of block.matchAll(pattern)) {
    out.push({ id: match[1], name: match[2], detail: match[3] });
  }
  return out;
}

describe("digiquantPipeline", () => {
  const source = readFileSync(ORIGINAL, "utf8");

  it("matches the research phases in the digiquant original", () => {
    expect(RESEARCH_PHASES).toEqual(extractTupleList(source, "RESEARCH"));
  });

  it("matches the portfolio phases in the digiquant original", () => {
    expect(PORTFOLIO_PHASES).toEqual(extractTupleList(source, "PORTFOLIO"));
  });

  it("counts only phases that ship", () => {
    expect(PIPELINE_PHASES).toHaveLength(RESEARCH_PHASES.length + PORTFOLIO_PHASES.length);
    expect(PIPELINE_PHASES).toHaveLength(19);
  });

  it("leaves execution without phases", () => {
    const execution = PIPELINE_ENGINES.find((e) => e.id === "execution");
    expect(execution?.phases).toEqual([]);
    expect(PIPELINE_PHASES.map((p) => p.id)).not.toContain("execution");
  });
});
