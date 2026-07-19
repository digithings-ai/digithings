import { describe, it, expect } from 'vitest';
import { PIPELINE_TOPOLOGY, pipelineNodeExplanation, stageById } from './pipeline-topology';

describe('pipeline topology', () => {
  it('has the six stages in pipeline order (learning = post-decision beliefs fold)', () => {
    expect(PIPELINE_TOPOLOGY.map((s) => s.id)).toEqual([
      'inputs', 'research', 'synthesis', 'selection', 'decision', 'learning',
    ]);
  });
  it('research carries the documented fan-outs (11 sectors per atlas/config/sectors.yaml)', () => {
    const research = stageById('research')!;
    const fanouts = Object.fromEntries(
      research.subSteps.filter((s) => s.fanout).map((s) => [s.id, s.fanout!.defaultCount]),
    );
    expect(fanouts).toMatchObject({ 'alt-data': 6, sectors: 11 });
  });
  it('sector scorecard is a research leaf (Phase-5 equities output), not a synthesis one', () => {
    expect(stageById('research')!.subSteps.map((s) => s.id)).toContain('scorecard');
    expect(stageById('synthesis')!.subSteps.map((s) => s.id)).not.toContain('scorecard');
  });
  it('selection has analysts and deliberation fan-outs and a commit-free spine', () => {
    const sel = stageById('selection')!;
    expect(sel.subSteps.map((s) => s.id)).toEqual([
      'thesis', 'screener', 'analysts', 'deliberation', 'pm-direction', 'risk-sizing',
    ]);
    expect(sel.subSteps.find((s) => s.id === 'analysts')!.fanout).toBeTruthy();
  });
  it('state-only steps (backend publishes no document, ever) are flagged', () => {
    const stateOnly = PIPELINE_TOPOLOGY.flatMap((s) =>
      s.subSteps.filter((sub) => sub.stateOnly).map((sub) => sub.id),
    );
    expect(stateOnly).toEqual(['preflight', 'consolidate', 'thesis', 'screener']);
  });
  it('learning stage holds the on-demand beliefs fold (#1383)', () => {
    expect(stageById('learning')!.subSteps.map((s) => s.id)).toEqual(['beliefs']);
  });

  it('explains every stage and sub-step for the guided pipeline view', () => {
    for (const stage of PIPELINE_TOPOLOGY) {
      expect(stage.description.length).toBeGreaterThan(20);
      for (const subStep of stage.subSteps) {
        expect(subStep.description.length).toBeGreaterThan(20);
      }
    }
  });

  it('resolves stage and granular step explanations from layout node ids', () => {
    expect(pipelineNodeExplanation('selection', 'selection')?.title).toBe('Selection');
    expect(
      pipelineNodeExplanation('selection', 'selection:deliberation')?.description,
    ).toMatch(/challenge|debate|deliberat/i);
  });
});
