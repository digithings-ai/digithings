import type { StageName } from "@/lib/run-snapshot";

/** Stage copy for the pipeline band. Verified against apps/dashboard/lib/pipeline-topology.ts
 *  (PIPELINE_TOPOLOGY: stage descriptions and sub-step labels, which mirror the backend graph in
 *  digiquant/src/digiquant/research/phases and graph/pipeline.py). Reworded only for length; no
 *  claim here goes beyond what that file says the stage does. The dashboard hides the `commit`
 *  sub-step from its graph, but it is the real Decision artifact (`commit-run/*`). */
export interface StageCopy {
  /** What the stage does, from the dashboard topology. */
  does: string;
  /** Sub-step labels in run order, from the dashboard topology. */
  steps: readonly string[];
}

export const STAGE_COPY: Record<StageName, StageCopy> = {
  Inputs: {
    does: "Validates the market and reference data required before any research work begins.",
    steps: ["Preflight / market data", "Attention plan (shadow, conditional)"],
  },
  Research: {
    does: "Runs independent specialist reads before combining evidence into a common market view.",
    steps: ["Alt-data", "Institutional", "Macro", "Asset-classes", "Sectors"],
  },
  Synthesis: {
    does: "Reconciles the research set into one directional read and a daily narrative for decision-makers.",
    steps: ["Consolidate bias", "Daily digest"],
  },
  Selection: {
    does: "Turns the synthesized view into challenged, screened, and risk-sized portfolio candidates.",
    steps: ["Thesis framing", "Screener", "Analysts", "Deliberation", "PM direction", "Risk sizing"],
  },
  Decision: {
    does: "Records the final recommendation and the evidence chain that produced it for this run.",
    steps: ["Commit"],
  },
  Learning: {
    does: "Folds resolved outcomes into a same-date beliefs document on every house run.",
    steps: ["Beliefs fold"],
  },
};
