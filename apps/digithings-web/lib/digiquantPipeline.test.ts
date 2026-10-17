import { describe, expect, it } from "vitest";
import { PIPELINE_ENGINES, PIPELINE_PHASES, PORTFOLIO_PHASES, RESEARCH_PHASES } from "./digiquantPipeline";

/**
 * digiquant-web's landing PipelineScene (the old source of truth these lists
 * were copied from) was removed on the Surfaces 1.0 branch, so this module is
 * now the only copy and there is nothing on disk to diff against.
 */

describe("digiquantPipeline", () => {
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
