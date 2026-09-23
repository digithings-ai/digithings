/**
 * digiquant's research → portfolio → execution phases, for the landing band.
 *
 * These are a *copy* of `apps/digiquant-web/app/_pipeline.ts`, which is the
 * single source of truth for the digiquant site (#4430) and is itself pinned to
 * the real graph by `apps/digiquant-web/components/landing/pipeline-data.test.ts`.
 *
 * A copy, not an import, because `apps/digiquant-web` is a separate Next app
 * root: its `@/app/_pipeline` specifier resolves through its own tsconfig and
 * cannot be reached from `apps/digithings-web`. The alternative — moving the
 * data into `packages/ui` — would put a digiquant-site contract inside the shared
 * kit and force the other app's test to change with it.
 *
 * So the copy is guarded instead: `digiquantPipeline.test.ts` reads the original
 * from disk and fails if the two disagree, which is the same protection an import
 * would have given without the cross-app coupling.
 *
 * Execution deliberately has no phases. Routing is off by default and no live
 * venue is wired, so the band shows the stage and says so rather than drawing
 * folders that do not exist.
 */

export type PipelineEngineId = "research" | "portfolio" | "execution";

export interface DashboardPhase {
  /** The real phase-folder id. */
  id: string;
  name: string;
  /** One line of mechanism. */
  detail: string;
}

export interface DashboardEngine {
  id: PipelineEngineId;
  label: string;
  /** One sentence describing what the engine does, from the digiquant site. */
  summary: string;
  phases: readonly DashboardPhase[];
}

export const RESEARCH_PHASES: readonly DashboardPhase[] = [
  { id: "00", name: "Preflight", detail: "config + data-layer check" },
  { id: "01", name: "Triage", detail: "what changed since last run" },
  { id: "02", name: "Alt-data", detail: "sentiment, flows, on-chain" },
  { id: "03", name: "Institutional", detail: "positioning & 13F flow" },
  { id: "04", name: "Macro", detail: "rates, liquidity, regime" },
  { id: "05", name: "Asset class", detail: "cross-asset context" },
  { id: "06", name: "Equities", detail: "sector & single-name" },
  { id: "07", name: "Consolidate", detail: "merge the evidence" },
  { id: "08", name: "Synthesis", detail: "ranked theses" },
  { id: "09", name: "Publish", detail: "to the thesis store" },
];

export const PORTFOLIO_PHASES: readonly DashboardPhase[] = [
  { id: "h1", name: "Thesis review", detail: "inherit & re-score" },
  { id: "h2", name: "Market thesis", detail: "exploration" },
  { id: "h3", name: "Vehicle map", detail: "thesis → instruments" },
  { id: "h4", name: "Screener", detail: "opportunity filter" },
  { id: "h45", name: "Coverage director", detail: "refresh, explore, or skip" },
  { id: "h5", name: "Asset analyst", detail: "per-name workup" },
  { id: "h6", name: "Deliberation", detail: "multi-agent debate" },
  { id: "h7", name: "PM direction", detail: "allocate & gate" },
  { id: "h8", name: "Risk sizing", detail: "½-Kelly, ceilings" },
  { id: "h9", name: "Commit run", detail: "persist & evolve" },
];

export const PIPELINE_ENGINES: readonly DashboardEngine[] = [
  {
    id: "research",
    label: "Research",
    summary:
      "Ten phases turn alt-data, institutional flow and macro into evidence-linked theses — every claim traceable to its source.",
    phases: RESEARCH_PHASES,
  },
  {
    id: "portfolio",
    label: "Portfolio",
    summary:
      "Thesis review to committed run — multi-agent deliberation, PM direction and risk sizing, with the dissent on record.",
    phases: PORTFOLIO_PHASES,
  },
  {
    id: "execution",
    label: "Execution",
    summary:
      "Paper routing is ready. Connecting a live venue is your own integration, not a flag we flip — so no phase folders ship here yet.",
    phases: [],
  },
];

/** Every phase that actually ships. */
export const PIPELINE_PHASES: readonly DashboardPhase[] = PIPELINE_ENGINES.flatMap(
  (engine) => engine.phases,
);
