export type PipelineStageId =
  | 'inputs'
  | 'research'
  | 'synthesis'
  | 'selection'
  | 'decision'
  | 'learning';

export interface FanoutDescriptor { id: string; label: string; defaultCount: number; }
export interface SubStep {
  id: string;
  label: string;
  fanout?: FanoutDescriptor;
  /**
   * The backend runs this step but never publishes a `documents` row for it
   * (state-only LangGraph node) — the node is expected to be inert every day,
   * not just on days with missing data.
   */
  stateOnly?: boolean;
}
export interface StageDef { id: PipelineStageId; label: string; subSteps: SubStep[]; }

// Mirrors the real backend graph: Atlas phases (preflight → research fan-outs →
// consolidate → digest) then Hermes H1–H9 (thesis framing → screener → analysts →
// deliberation → PM direction → risk sizing → commit) then the on-demand beliefs
// fold (learning/beliefs_distillation.py, runs after the terminal publish).
export const PIPELINE_TOPOLOGY: StageDef[] = [
  { id: 'inputs', label: 'Inputs', subSteps: [
    { id: 'preflight', label: 'Preflight / market data', stateOnly: true },
  ]},
  { id: 'research', label: 'Research', subSteps: [
    { id: 'alt-data', label: 'Alt-data', fanout: { id: 'alt-data', label: 'Alt-data', defaultCount: 6 } },
    { id: 'institutional', label: 'Institutional', fanout: { id: 'institutional', label: 'Institutional', defaultCount: 2 } },
    { id: 'macro', label: 'Macro' },
    { id: 'asset-classes', label: 'Asset-classes', fanout: { id: 'asset-classes', label: 'Asset-classes', defaultCount: 6 } },
    // 11 slugs in atlas/config/sectors.yaml (sector-technology … sector-comms).
    { id: 'sectors', label: 'Sectors', fanout: { id: 'sectors', label: 'Sectors', defaultCount: 11 } },
    // Phase-5 equities output — published as `sector-scorecard` (category "sector"),
    // a research artifact, NOT the Phase-6 consolidate output it was once wired to.
    { id: 'scorecard', label: 'Sector scorecard' },
  ]},
  { id: 'synthesis', label: 'Synthesis', subSteps: [
    // Phase 6 emits only the in-state bias row (phase6_bias_row) — no document.
    { id: 'consolidate', label: 'Consolidate bias', stateOnly: true },
    { id: 'digest', label: 'Daily digest' },
  ]},
  { id: 'selection', label: 'Selection', subSteps: [
    // H1–H3 build thesis documents into state slots only; H4 screener likewise.
    { id: 'thesis', label: 'Thesis framing', stateOnly: true },
    { id: 'screener', label: 'Screener', stateOnly: true },
    { id: 'analysts', label: 'Analysts', fanout: { id: 'analysts', label: 'Analysts', defaultCount: 0 } },
    { id: 'deliberation', label: 'Deliberation', fanout: { id: 'deliberation', label: 'Deliberation', defaultCount: 0 } },
    { id: 'pm-direction', label: 'PM direction' },
    { id: 'risk-sizing', label: 'Risk sizing' },
  ]},
  { id: 'decision', label: 'Decision', subSteps: [
    { id: 'commit', label: 'Commit' },
  ]},
  { id: 'learning', label: 'Learning', subSteps: [
    // On-demand beliefs distillation (#1383): publishes document_key `beliefs`
    // only on trigger days (resolved backlog > threshold or refresh_scope=beliefs),
    // so the node renders inert on most days — that is expected, not drift.
    { id: 'beliefs', label: 'Beliefs fold' },
  ]},
];

export function stageById(id: PipelineStageId): StageDef | undefined {
  return PIPELINE_TOPOLOGY.find((s) => s.id === id);
}
