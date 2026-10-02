/**
 * digiquant's pipeline stages, for any digithings.ai surface that lists them.
 *
 * These are a *copy* of `apps/digiquant-web/app/_stages.ts` and
 * `apps/digiquant-web/components/pipeline/stage-copy.ts`. The homepage banner
 * (`apps/digiquant-web/app/_bands/pipeline.tsx`) is a separate four-workflow
 * section and does not render this catalog. The two apps are separate Next
 * roots, so this file cannot import the original.
 *
 * `digiquantPipeline.test.ts` reads those files from disk and fails if the
 * copy drifts. The fix is to copy the change across. Do not invent a stage,
 * a step, or a description that is not already in those files.
 *
 * Execution is not a stage. `_stages.ts` shows it separately, in development.
 */

export interface PipelineStage {
  name: string;
  /** What the stage does, from stage-copy.ts. */
  does: string;
  /** Sub-step labels in run order, from stage-copy.ts. */
  steps: readonly string[];
}

export const PIPELINE_STAGES: readonly PipelineStage[] = [
  {
    name: "Inputs",
    does: "Validates the market and reference data required before any research work begins.",
    steps: ["Preflight / market data", "Attention plan (shadow, conditional)"],
  },
  {
    name: "Research",
    does: "Runs independent specialist reads before combining evidence into a common market view.",
    steps: ["Alt-data", "Institutional", "Macro", "Asset-classes", "Sectors"],
  },
  {
    name: "Synthesis",
    does: "Reconciles the research set into one directional read and a daily narrative for decision-makers.",
    steps: ["Consolidate bias", "Daily digest"],
  },
  {
    name: "Selection",
    does: "Turns the synthesized view into challenged, screened, and risk-sized portfolio candidates.",
    steps: ["Thesis framing", "Screener", "Analysts", "Deliberation", "PM direction", "Risk sizing"],
  },
  {
    name: "Decision",
    does: "Records the final recommendation and the evidence chain that produced it for this run.",
    steps: ["Commit"],
  },
  {
    name: "Learning",
    does: "Folds resolved outcomes into a same-date beliefs document on every house run.",
    steps: ["Beliefs fold"],
  },
];

export const EXECUTION = { name: "Execution", status: "in development" } as const;
