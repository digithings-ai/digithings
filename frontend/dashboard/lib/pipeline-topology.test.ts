import { describe, it, expect } from 'vitest';
import { PIPELINE_TOPOLOGY, pipelineNodeExplanation, stageById } from './pipeline-topology';

describe('pipeline topology', () => {
  it('has the six stages in pipeline order (learning = post-decision beliefs fold)', () => {
    expect(PIPELINE_TOPOLOGY.map((s) => s.id)).toEqual([
      'inputs', 'research', 'synthesis', 'selection', 'decision', 'learning',
    ]);
  });
  it('research carries the documented fan-outs (11 sectors per research/config/sectors.yaml)', () => {
    const research = stageById('research')!;
    const fanouts = Object.fromEntries(
      research.subSteps.filter((s) => s.fanout).map((s) => [s.id, s.fanout!.defaultCount]),
    );
    expect(fanouts).toMatchObject({ 'alt-data': 6, sectors: 11 });
  });
  it('research has no sector-scorecard leaf; sector memos live under the sectors fan-out', () => {
    expect(stageById('research')!.subSteps.map((s) => s.id)).not.toContain('scorecard');
    expect(stageById('research')!.subSteps.map((s) => s.id)).toContain('sectors');
    expect(stageById('synthesis')!.subSteps.map((s) => s.id)).not.toContain('scorecard');
  });
  it('selection has analysts and deliberation fan-outs and a commit-free spine', () => {
    const sel = stageById('selection')!;
    expect(sel.subSteps.map((s) => s.id)).toEqual([
      'thesis', 'screener', 'analysts', 'deliberation', 'pm-direction', 'risk-sizing',
    ]);
    expect(sel.subSteps.find((s) => s.id === 'analysts')!.fanout).toBeTruthy();
  });
  it('no longer flags preflight/consolidate/thesis/screener as state-only (WP-B documents)', () => {
    const stateOnly = PIPELINE_TOPOLOGY.flatMap((s) =>
      s.subSteps.filter((sub) => sub.stateOnly).map((sub) => sub.id),
    );
    expect(stateOnly).toEqual([]);
  });
  it('inputs includes attention-plan glass-box leaf (#1945)', () => {
    expect(stageById('inputs')!.subSteps.map((s) => s.id)).toEqual([
      'preflight',
      'attention-plan',
    ]);
    expect(stageById('inputs')!.subSteps.find((s) => s.id === 'attention-plan')!.conditionalArtifact)
      .toBe(true);
  });
  it('learning stage holds the daily beliefs fold (WP-I)', () => {
    expect(stageById('learning')!.subSteps.map((s) => s.id)).toEqual(['beliefs']);
    expect(stageById('learning')!.subSteps[0]!.conditionalArtifact).toBeUndefined();
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

  it('hides commit from the operator graph (ledger-only commit-run)', () => {
    expect(stageById('decision')!.subSteps.find((s) => s.id === 'commit')?.hiddenFromGraph).toBe(true);
  });
});
