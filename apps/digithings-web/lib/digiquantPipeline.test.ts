import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { EXECUTION, PIPELINE_STAGES } from "./digiquantPipeline";

/**
 * The digithings.ai stage list is a copy of the digiquant.io pipeline band,
 * because the two live in separate Next app roots and neither can import the
 * other's modules. A copy that can silently drift is worse than no copy, so
 * this test reads the original from disk and compares.
 *
 * If it fails, the fix is to copy the change across — not to relax the test,
 * and not to invent a stage. Source of truth:
 * `apps/digiquant-web/app/_stages.ts` (names) and
 * `apps/digiquant-web/components/pipeline/stage-copy.ts` (does + steps),
 * rendered by `apps/digiquant-web/app/_bands/pipeline.tsx`.
 */

const WEB = resolve(__dirname, "..", "..", "digiquant-web");
const STAGES = resolve(WEB, "app", "_stages.ts");
const COPY = resolve(WEB, "components", "pipeline", "stage-copy.ts");
const BAND = resolve(WEB, "app", "_bands", "pipeline.tsx");

type Stage = { name: string; does: string; steps: string[] };

function quoted(block: string): string[] {
  return [...block.matchAll(/"([^"]+)"/g)].map((match) => match[1]);
}

function stageNames(source: string): string[] {
  const start = source.indexOf("export const PIPELINE_STAGES");
  expect(start, "PIPELINE_STAGES not found in _stages.ts").toBeGreaterThan(-1);
  const end = source.indexOf("]", start);
  return quoted(source.slice(start, end));
}

function execution(source: string): { name: string; status: string } {
  const start = source.indexOf("export const EXECUTION_STAGE");
  expect(start, "EXECUTION_STAGE not found in _stages.ts").toBeGreaterThan(-1);
  const end = source.indexOf(";", start);
  const block = source.slice(start, end);
  const name = block.match(/name:\s*"([^"]+)"/);
  const status = block.match(/status:\s*"([^"]+)"/);
  expect(name?.[1]).toBeTruthy();
  expect(status?.[1]).toBeTruthy();
  return { name: name![1], status: status![1] };
}

function stageCopy(source: string): Stage[] {
  const start = source.indexOf("export const STAGE_COPY");
  expect(start, "STAGE_COPY not found in stage-copy.ts").toBeGreaterThan(-1);
  const body = source.slice(start);
  const pattern = /(\w+):\s*\{\s*does:\s*"([^"]+)",\s*steps:\s*\[([\s\S]*?)\]/g;
  const out: Stage[] = [];
  for (const match of body.matchAll(pattern)) {
    out.push({ name: match[1], does: match[2], steps: quoted(match[3]) });
  }
  expect(out.length).toBeGreaterThan(0);
  return out;
}

describe("digiquantPipeline", () => {
  const stagesSrc = readFileSync(STAGES, "utf8");
  const copySrc = readFileSync(COPY, "utf8");
  const bandSrc = readFileSync(BAND, "utf8");

  it("matches the stage names the digiquant pipeline band renders", () => {
    expect(bandSrc).toContain("PIPELINE_STAGES.map");
    expect(bandSrc).toContain("EXECUTION_STAGE.status");
    expect(PIPELINE_STAGES.map((stage) => stage.name)).toEqual(stageNames(stagesSrc));
  });

  it("matches the stage copy, including the step labels", () => {
    expect(PIPELINE_STAGES).toEqual(stageCopy(copySrc));
  });

  it("leaves execution as the separate in-development stage", () => {
    expect(EXECUTION).toEqual(execution(stagesSrc));
    expect(PIPELINE_STAGES.map((stage) => stage.name)).not.toContain(EXECUTION.name);
  });
});
