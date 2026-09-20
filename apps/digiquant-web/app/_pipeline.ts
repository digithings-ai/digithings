/**
 * Single source of truth for digiquant's research → portfolio pipeline
 * (#4430). One data file feeds BOTH the homepage chip gallery and the metrics
 * band, so the two can never disagree about how many phases ship — the plan's
 * old "16 phases" / "7 pipeline stages" pair was self-contradicting, and this
 * file replaces both numbers with the real phase folders.
 *
 * The ids are the REAL internal phase-folder names, not a sequential count
 * (#4430 ground truth): `digiquant/src/digiquant/research/phases/` holds ten
 * phase entry points, `digiquant/src/digiquant/portfolio/phases/` holds nine.
 * The portfolio sequence runs h7 → h7e → h9 with no h8 because that number was
 * never assigned a phase — a gap in the internal naming, not a missing step.
 *
 * Execution has no phase folders yet: it is marked "in development" and its
 * `phases` array is deliberately empty, so `PIPELINE_PHASES.length` counts only
 * what actually runs.
 */

export type PipelineEngine = "research" | "portfolio" | "execution";

export interface PipelinePhase {
  /** The real phase-folder id, surfaced as the keycap chip. */
  id: string;
  name: string;
  /** One line of mechanism, ≤ 8 words where possible. */
  detail: string;
}

export interface PipelineEngineGroup {
  id: PipelineEngine;
  label: string;
  /** One sentence describing what the engine does. */
  summary: string;
  /** Empty for execution — it ships after the book is committed. */
  phases: readonly PipelinePhase[];
}

/** Research phases, in run order (`research/phases/*`). */
export const RESEARCH_PHASES: readonly PipelinePhase[] = [
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

/** Portfolio / deliberation phases, in run order (`portfolio/phases/*`). */
export const PORTFOLIO_PHASES: readonly PipelinePhase[] = [
  { id: "h1", name: "Thesis review", detail: "inherit & re-score" },
  { id: "h2", name: "Market thesis", detail: "exploration" },
  { id: "h3", name: "Vehicle map", detail: "thesis → instruments" },
  { id: "h4", name: "Screener", detail: "opportunity filter" },
  { id: "h5", name: "Asset analyst", detail: "per-name workup" },
  { id: "h6", name: "Deliberation", detail: "multi-agent debate" },
  { id: "h7", name: "PM direction", detail: "allocate & gate" },
  { id: "h7e", name: "Risk sizing", detail: "½-Kelly, ceilings" },
  { id: "h9", name: "Commit run", detail: "persist & evolve" },
];

export const PIPELINE_ENGINES: readonly PipelineEngineGroup[] = [
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

/** Every phase that actually ships — the derived count the metrics band reads. */
export const PIPELINE_PHASES: readonly PipelinePhase[] = PIPELINE_ENGINES.flatMap(
  (e) => e.phases,
);

/**
 * Live orders sent to a venue. Zero by design: routing is off by default, live
 * venue tokens are refused, and nothing is wired to a venue yet. Kept here so
 * the metric and the prose cannot drift.
 */
export const LIVE_ORDERS = 0;
