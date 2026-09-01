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
  description: string;
  fanout?: FanoutDescriptor;
  /**
   * The backend runs this step but never publishes a `documents` row for it
   * (state-only LangGraph node) — the node is expected to be inert every day,
   * not just on days with missing data.
   */
  stateOnly?: boolean;
  /** Publishes an artifact only when its trigger fires; absence is not a failed persistence. */
  conditionalArtifact?: boolean;
  /**
   * Ledger/status only — do not emit this sub-step on the operator graph.
   * Clicking the parent stage must not open this node as a reading surface.
   */
  hiddenFromGraph?: boolean;
}
export interface StageDef {
  id: PipelineStageId;
  label: string;
  description: string;
  subSteps: SubStep[];
}

export interface PipelineNodeExplanation {
  title: string;
  description: string;
  stageLabel: string;
  stageNumber: number;
  behavior: 'Stage overview' | 'Parallel dispatch' | 'In-memory operation' | 'Run artifact';
}

// Mirrors the real backend graph: Atlas phases (preflight → research fan-outs →
// consolidate → digest) then Hermes H1–H9 (thesis framing → screener → analysts →
// deliberation → PM direction → risk sizing → commit) then the on-demand beliefs
// fold (learning/beliefs_distillation.py, runs after the terminal publish).
export const PIPELINE_TOPOLOGY: StageDef[] = [
  {
    id: 'inputs',
    label: 'Inputs',
    description: 'Validates the market and reference data required before any research work begins.',
    subSteps: [
    {
      id: 'preflight',
      label: 'Preflight / market data',
      description: 'Checks that the run has complete, current inputs and records readiness in pipeline state.',
    },
    // WP13-class AttentionPlan shadow (#1945 glass-box): published as
    // `attention-plan` when the shadow planner runs. Absence is expected until
    // graph wiring lands — treat like beliefs (conditional), not a persistence miss.
    {
      id: 'attention-plan',
      label: 'Attention plan',
      description:
        'Records which artifacts the shadow planner would refresh and why, under the pinned ProfileConfig, without actuating routing.',
      conditionalArtifact: true,
    },
  ]},
  {
    id: 'research',
    label: 'Research',
    description: 'Runs independent specialist reads before combining evidence into a common market view.',
    subSteps: [
    {
      id: 'alt-data',
      label: 'Alt-data',
      description: 'Dispatches independent alternative-data reads to surface signals outside price and fundamentals.',
      fanout: { id: 'alt-data', label: 'Alt-data', defaultCount: 6 },
    },
    {
      id: 'institutional',
      label: 'Institutional',
      description: 'Collects institutional research perspectives so the run can compare external desk views.',
      fanout: { id: 'institutional', label: 'Institutional', defaultCount: 2 },
    },
    {
      id: 'macro',
      label: 'Macro',
      description: 'Frames growth, inflation, policy, and risk appetite as the macro context for the run.',
    },
    {
      id: 'asset-classes',
      label: 'Asset-classes',
      description: 'Dispatches parallel specialists across configured asset classes to produce comparable reads.',
      fanout: { id: 'asset-classes', label: 'Asset-classes', defaultCount: 6 },
    },
    // 11 slugs in atlas/config/sectors.yaml (sector-technology … sector-comms).
    {
      id: 'sectors',
      label: 'Sectors',
      description: 'Dispatches sector specialists in parallel to compare leadership, risk, and relative opportunity.',
      fanout: { id: 'sectors', label: 'Sectors', defaultCount: 11 },
    },
  ]},
  {
    id: 'synthesis',
    label: 'Synthesis',
    description: 'Reconciles the research set into one directional read and a daily narrative for decision-makers.',
    subSteps: [
    // Phase 6 bias row is published as `bias-row` from Atlas publish_phase.
    {
      id: 'consolidate',
      label: 'Consolidate bias',
      description: 'Combines specialist signals into the directional bias carried forward in pipeline state.',
    },
    {
      id: 'digest',
      label: 'Daily digest',
      description: 'Publishes the synthesized market read, key evidence, and changes that frame the daily run.',
    },
  ]},
  {
    id: 'selection',
    label: 'Selection',
    description: 'Turns the synthesized view into challenged, screened, and risk-sized portfolio candidates.',
    subSteps: [
    // H1 publishes `thesis/thesis-review`; H4 publishes `opportunity-screener`.
    {
      id: 'thesis',
      label: 'Thesis framing',
      description: 'Frames candidate investment theses and the evidence each candidate must satisfy.',
    },
    {
      id: 'screener',
      label: 'Screener',
      description: 'Applies the run criteria to narrow the candidate set before deeper analyst work.',
    },
    {
      id: 'analysts',
      label: 'Analysts',
      description: 'Dispatches independent analyst rounds across surviving candidates to build distinct cases.',
      fanout: { id: 'analysts', label: 'Analysts', defaultCount: 0 },
    },
    {
      id: 'deliberation',
      label: 'Deliberation',
      description: 'Challenges and debates the analyst cases to surface disagreement, weak evidence, and trade-offs.',
      fanout: { id: 'deliberation', label: 'Deliberation', defaultCount: 0 },
    },
    {
      id: 'pm-direction',
      label: 'PM direction',
      description: 'Translates the deliberated cases into a portfolio-manager direction for the run.',
    },
    {
      id: 'risk-sizing',
      label: 'Risk sizing',
      description: 'Converts the selected direction into position sizes constrained by the portfolio risk budget.',
    },
  ]},
  {
    id: 'decision',
    label: 'Decision',
    description: 'Records the final recommendation and the evidence chain that produced it for this run.',
    subSteps: [
    {
      id: 'commit',
      label: 'Commit',
      description: 'Publishes the final run decision and its traceable commit record for inspection.',
      hiddenFromGraph: true,
    },
  ]},
  {
    id: 'learning',
    label: 'Learning',
    description: 'Folds resolved outcomes back into durable beliefs when the learning trigger is active.',
    subSteps: [
    // On-demand beliefs distillation (#1383): publishes document_key `beliefs`
    // only on trigger days (resolved backlog > threshold or refresh_scope=beliefs),
    // so the node renders inert on most days — that is expected, not drift.
    {
      id: 'beliefs',
      label: 'Beliefs fold',
      description: 'Distills eligible resolved evidence into updated beliefs for use by future runs.',
      conditionalArtifact: true,
    },
  ]},
];

export function stageById(id: PipelineStageId): StageDef | undefined {
  return PIPELINE_TOPOLOGY.find((s) => s.id === id);
}

export function pipelineNodeExplanation(
  stageId: PipelineStageId,
  nodeId: string,
): PipelineNodeExplanation | null {
  const stageNumber = PIPELINE_TOPOLOGY.findIndex((stage) => stage.id === stageId) + 1;
  const stage = stageById(stageId);
  if (!stage || stageNumber === 0) return null;

  if (nodeId === stageId) {
    return {
      title: stage.label,
      description: stage.description,
      stageLabel: stage.label,
      stageNumber,
      behavior: 'Stage overview',
    };
  }

  const subStepId = nodeId.split(':')[1];
  const subStep = stage.subSteps.find((candidate) => candidate.id === subStepId);
  if (!subStep) return null;

  return {
    title: subStep.label,
    description: subStep.description,
    stageLabel: stage.label,
    stageNumber,
    behavior: subStep.fanout
      ? 'Parallel dispatch'
      : subStep.stateOnly
        ? 'In-memory operation'
        : 'Run artifact',
  };
}
