import { describe, it, expect } from 'vitest';
import { PIPELINE_TOPOLOGY, stageById } from './pipeline-topology';

describe('pipeline topology', () => {
  it('has the five stages in pipeline order', () => {
    expect(PIPELINE_TOPOLOGY.map((s) => s.id)).toEqual([
      'inputs', 'research', 'synthesis', 'selection', 'decision',
    ]);
  });
  it('research carries the documented fan-outs', () => {
    const research = stageById('research')!;
    const fanouts = Object.fromEntries(
      research.subSteps.filter((s) => s.fanout).map((s) => [s.id, s.fanout!.defaultCount]),
    );
    expect(fanouts).toMatchObject({ 'alt-data': 6, sectors: 12 });
  });
  it('selection has analysts and deliberation fan-outs and a commit-free spine', () => {
    const sel = stageById('selection')!;
    expect(sel.subSteps.map((s) => s.id)).toEqual([
      'thesis', 'screener', 'analysts', 'deliberation', 'pm-direction', 'risk-sizing',
    ]);
    expect(sel.subSteps.find((s) => s.id === 'analysts')!.fanout).toBeTruthy();
  });
});
