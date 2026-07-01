export type PipelineStageId = 'inputs' | 'research' | 'synthesis' | 'selection' | 'decision';

export interface FanoutDescriptor { id: string; label: string; defaultCount: number; }
export interface SubStep { id: string; label: string; fanout?: FanoutDescriptor; }
export interface StageDef { id: PipelineStageId; label: string; subSteps: SubStep[]; }

export const PIPELINE_TOPOLOGY: StageDef[] = [
  { id: 'inputs', label: 'Inputs', subSteps: [
    { id: 'preflight', label: 'Preflight / market data' },
  ]},
  { id: 'research', label: 'Research', subSteps: [
    { id: 'alt-data', label: 'Alt-data', fanout: { id: 'alt-data', label: 'Alt-data', defaultCount: 6 } },
    { id: 'institutional', label: 'Institutional', fanout: { id: 'institutional', label: 'Institutional', defaultCount: 2 } },
    { id: 'macro', label: 'Macro' },
    { id: 'asset-classes', label: 'Asset-classes', fanout: { id: 'asset-classes', label: 'Asset-classes', defaultCount: 6 } },
    { id: 'sectors', label: 'Sectors', fanout: { id: 'sectors', label: 'Sectors', defaultCount: 12 } },
  ]},
  { id: 'synthesis', label: 'Synthesis', subSteps: [
    { id: 'consolidate', label: 'Consolidate bias' },
    { id: 'digest', label: 'Daily digest' },
  ]},
  { id: 'selection', label: 'Selection', subSteps: [
    { id: 'thesis', label: 'Thesis framing' },
    { id: 'screener', label: 'Screener' },
    { id: 'analysts', label: 'Analysts', fanout: { id: 'analysts', label: 'Analysts', defaultCount: 0 } },
    { id: 'deliberation', label: 'Deliberation', fanout: { id: 'deliberation', label: 'Deliberation', defaultCount: 0 } },
    { id: 'pm-direction', label: 'PM direction' },
    { id: 'risk-sizing', label: 'Risk sizing' },
  ]},
  { id: 'decision', label: 'Decision', subSteps: [
    { id: 'commit', label: 'Commit' },
  ]},
];

export function stageById(id: PipelineStageId): StageDef | undefined {
  return PIPELINE_TOPOLOGY.find((s) => s.id === id);
}
