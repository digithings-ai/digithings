/** Phase 0-owned, frozen shape: the single source for pipeline stage names and
 *  counts (hero counter, pipeline band, snapshot). Stages are the dashboard's
 *  six; execution is shown separately and is not built. */
export const PIPELINE_STAGES = ["Inputs", "Research", "Synthesis", "Selection", "Decision", "Learning"] as const;

export const EXECUTION_STAGE = { name: "Execution", status: "in development" } as const;
