import { describe, it, expect } from 'vitest';
import { layoutPipeline } from './pipeline-layout';
import type { ExpansionState } from './pipeline-layout';
import type { PipelineDayData } from './pipeline-graph-data';

const emptyDay: PipelineDayData = {
  fanoutCounts: { sectors: 11 },
  fanoutKeys: {},
  presentKeys: new Set<string>(),
  artifacts: [],
};
const collapsed: ExpansionState = { expandedStages: new Set(), expandedFanouts: new Set() };

describe('layoutPipeline', () => {
  it('collapsed: six stage nodes left to right, same row', () => {
    const l = layoutPipeline(emptyDay, collapsed);
    const stages = l.nodes.filter((n) => n.kind === 'stage');
    expect(stages).toHaveLength(6);
    const xs = stages.map((n) => n.x);
    expect([...xs]).toEqual([...xs].sort((a, b) => a - b)); // strictly increasing order preserved
    expect(new Set(stages.map((n) => n.y)).size).toBe(1);   // one row
    expect(stages.every((node) => node.runStatus === 'not-run')).toBe(true);
  });

  it('expanded research sub-steps share the stage x and stack in y', () => {
    const l = layoutPipeline(emptyDay, {
      expandedStages: new Set(['research']),
      expandedFanouts: new Set(),
    });
    const research = l.nodes.find((n) => n.id === 'research');
    expect(research).toBeDefined();
    const subs = l.nodes.filter((n) => n.kind === 'substep' && n.stageId === 'research');
    expect(subs.map((n) => n.label)).toEqual([
      'Alt-data',
      'Institutional',
      'Macro',
      'Asset-classes',
      'Sectors',
    ]);
    expect(subs.every((n) => n.x === research!.x)).toBe(true);
    const ys = subs.map((n) => n.y);
    expect(ys[0]).toBeGreaterThan(research!.y);
    expect([...ys]).toEqual([...ys].sort((a, b) => a - b));
    expect(new Set(ys).size).toBe(ys.length);

    const synthesis = l.nodes.find((n) => n.id === 'synthesis');
    expect(synthesis?.y).toBe(research!.y);
    expect(synthesis!.x).toBeGreaterThan(research!.x);
    expect(l.width).toBe(layoutPipeline(emptyDay, collapsed).width);
  });

  it('expanded fan-out branches stack under the parent row, pushing later siblings down', () => {
    const day: PipelineDayData = {
      fanoutCounts: { 'alt-data': 2 },
      fanoutKeys: { 'alt-data': ['alt-cta', 'alt-sentiment'] },
      presentKeys: new Set(['alt-cta', 'alt-sentiment']),
      artifacts: [],
    };
    const l = layoutPipeline(day, {
      expandedStages: new Set(['research']),
      expandedFanouts: new Set(['research:alt-data']),
    });
    const research = l.nodes.find((n) => n.id === 'research')!;
    const alt = l.nodes.find((n) => n.id === 'research:alt-data')!;
    const branches = l.nodes.filter(
      (n) => n.kind === 'fanout-branch' && n.id.startsWith('research:alt-data:'),
    );
    const inst = l.nodes.find((n) => n.id === 'research:institutional')!;

    expect(alt.x).toBe(research.x);
    expect(branches.map((n) => n.documentKey)).toEqual(['alt-cta', 'alt-sentiment']);
    expect(branches.every((b) => b.x === alt.x)).toBe(true);
    expect(branches[0].y).toBeGreaterThan(alt.y);
    expect(branches[1].y).toBeGreaterThan(branches[0].y);
    expect(inst.x).toBe(research.x);
    expect(inst.y).toBeGreaterThan(branches[branches.length - 1].y);
  });

  it('uses the snapshot marker when a recorded run published no documents', () => {
    const l = layoutPipeline(
      { ...emptyDay, runRecorded: true },
      { expandedStages: new Set(['synthesis']), expandedFanouts: new Set() },
    );
    expect(l.nodes.find((node) => node.id === 'synthesis:consolidate')?.runStatus)
      .toBe('expected-artifact-missing');
    expect(l.nodes.find((node) => node.id === 'synthesis:digest')?.runStatus)
      .toBe('expected-artifact-missing');
  });

  it('expanding sectors fan-out (no fanoutKeys) falls back to count-indexed branches with NO documentKey', () => {
    const exp: ExpansionState = {
      expandedStages: new Set(['research']),
      expandedFanouts: new Set(['research:sectors']),
    };
    const l = layoutPipeline(emptyDay, exp);
    const branches = l.nodes.filter((n) => n.kind === 'fanout-branch' && n.id.startsWith('research:sectors:'));
    expect(branches).toHaveLength(11);
    const ys = branches.map((n) => n.y);
    expect(new Set(branches.map((n) => n.x)).size).toBe(1); // same column
    expect([...ys]).toEqual([...ys].sort((a, b) => a - b)); // stacked downward
    expect(branches.every((b) => b.documentKey === undefined)).toBe(true);
  });

  it('emits one branch per real document_key with entity-suffix labels when fanoutKeys present', () => {
    const day: PipelineDayData = {
      fanoutCounts: { analysts: 2, sectors: 2, 'asset-classes': 2 },
      fanoutKeys: {
        analysts: ['analyst/QQQ', 'analyst/TLT'],
        sectors: ['sector-financials', 'sector-technology'],
        'asset-classes': ['bonds', 'crypto'],
      },
      presentKeys: new Set(['analyst/QQQ', 'analyst/TLT', 'sector-financials', 'sector-technology', 'bonds', 'crypto']),
      artifacts: [],
    };
    const exp: ExpansionState = {
      expandedStages: new Set(['research', 'selection']),
      expandedFanouts: new Set(['research:sectors', 'research:asset-classes', 'selection:analysts']),
    };
    const l = layoutPipeline(day, exp);

    const analysts = l.nodes.filter((n) => n.id.startsWith('selection:analysts:'));
    expect(analysts.map((n) => n.documentKey)).toEqual(['analyst/QQQ', 'analyst/TLT']);
    expect(analysts.map((n) => n.label)).toEqual(['QQQ', 'TLT']);

    const sectors = l.nodes.filter((n) => n.id.startsWith('research:sectors:'));
    expect(sectors.map((n) => n.documentKey)).toEqual(['sector-financials', 'sector-technology']);
    expect(sectors.map((n) => n.label)).toEqual(['financials', 'technology']);

    const assets = l.nodes.filter((n) => n.id.startsWith('research:asset-classes:'));
    expect(assets.map((n) => n.documentKey)).toEqual(['bonds', 'crypto']);
    expect(assets.map((n) => n.label)).toEqual(['bonds', 'crypto']);
  });

  it('leaf sub-steps get documentKey only when the key is present that day', () => {
    const day: PipelineDayData = {
      fanoutCounts: {},
      fanoutKeys: {},
      presentKeys: new Set(['macro', 'pm-direction-memo', 'sector-technology', 'beliefs', 'commit-run/123', 'commit-run/999']),
      artifacts: [],
    };
    const exp: ExpansionState = {
      expandedStages: new Set(['research', 'synthesis', 'selection', 'decision', 'learning']),
      expandedFanouts: new Set(),
    };
    const l = layoutPipeline(day, exp);
    const byId = (id: string) => l.nodes.find((n) => n.id === id);

    expect(byId('research:macro')?.documentKey).toBe('macro');
    expect(byId('research:macro')?.runStatus).toBe('persisted-artifact');
    expect(byId('selection:pm-direction')?.documentKey).toBe('pm-direction-memo');
    // digest absent that day -> no documentKey (golden rule)
    expect(byId('synthesis:digest')?.documentKey).toBeUndefined();
    expect(byId('synthesis:digest')?.runStatus).toBe('expected-artifact-missing');
    // sector memos are fan-out branches; the scorecard leaf is gone (WP-D)
    expect(byId('research:scorecard')).toBeUndefined();
    // consolidate is a real document once bias-row is present
    expect(byId('synthesis:consolidate')?.documentKey).toBeUndefined();
    expect(byId('synthesis:consolidate')?.stateOnly).toBeUndefined();
    expect(byId('synthesis:consolidate')?.runStatus).toBe('expected-artifact-missing');
    // beliefs fold resolves when the same-date daily document is present (WP-I)
    expect(byId('learning:beliefs')?.documentKey).toBe('beliefs');
    expect(byId('learning:beliefs')?.runStatus).toBe('persisted-artifact');
    // Decision collapses onto the booked book; commit-run is not a graph node.
    expect(byId('decision')?.documentKey).toBeUndefined();
    expect(byId('decision:commit')).toBeUndefined();
    expect(l.nodes.some((n) => n.documentKey?.startsWith('commit-run/'))).toBe(false);
    expect(byId('selection:thesis')?.documentKey).toBeUndefined();
    expect(byId('selection:thesis')?.stateOnly).toBeUndefined();
    expect(byId('selection:screener')?.documentKey).toBeUndefined();
  });

  it('WP-B leaves resolve documentKey when inputs/bias-row/thesis/screener are present', () => {
    const day: PipelineDayData = {
      fanoutCounts: {},
      fanoutKeys: {},
      presentKeys: new Set([
        'inputs',
        'bias-row',
        'thesis/thesis-review',
        'opportunity-screener',
        'macro',
      ]),
      artifacts: [],
    };
    const l = layoutPipeline(day, {
      expandedStages: new Set(['inputs', 'synthesis', 'selection']),
      expandedFanouts: new Set(),
    });
    const byId = (id: string) => l.nodes.find((n) => n.id === id);
    expect(byId('inputs:preflight')?.documentKey).toBe('inputs');
    expect(byId('inputs:preflight')?.runStatus).toBe('persisted-artifact');
    expect(byId('synthesis:consolidate')?.documentKey).toBe('bias-row');
    expect(byId('synthesis:consolidate')?.runStatus).toBe('persisted-artifact');
    expect(byId('selection:thesis')?.documentKey).toBe('thesis/thesis-review');
    expect(byId('selection:thesis')?.runStatus).toBe('persisted-artifact');
    expect(byId('selection:screener')?.documentKey).toBe('opportunity-screener');
    expect(byId('selection:screener')?.runStatus).toBe('persisted-artifact');
  });

  it('Decision stage focuses pm-rebalance and never exposes commit-run on the graph', () => {
    const day: PipelineDayData = {
      fanoutCounts: {},
      fanoutKeys: {},
      presentKeys: new Set(['pm-rebalance', 'commit-run/9999999999', 'commit-run/10000000000']),
      artifacts: [],
    };
    const l = layoutPipeline(day, {
      expandedStages: new Set(['decision', 'selection']),
      expandedFanouts: new Set(),
    });
    expect(l.nodes.find((n) => n.id === 'decision')?.documentKey).toBe('pm-rebalance');
    expect(l.nodes.find((n) => n.id === 'selection:risk-sizing')?.documentKey).toBe('pm-rebalance');
    expect(l.nodes.some((n) => n.id === 'decision:commit')).toBe(false);
    expect(l.nodes.some((n) => n.documentKey?.startsWith('commit-run/'))).toBe(false);
  });

  it('beliefs node has no documentKey until the same-date fold publishes', () => {
    const day: PipelineDayData = {
      fanoutCounts: {},
      fanoutKeys: {},
      presentKeys: new Set(['macro']),
      artifacts: [],
    };
    const exp: ExpansionState = {
      expandedStages: new Set(['learning']),
      expandedFanouts: new Set(),
    };
    const l = layoutPipeline(day, exp);
    const beliefs = l.nodes.find((n) => n.id === 'learning:beliefs');
    expect(beliefs?.documentKey).toBeUndefined();
    expect(beliefs?.runStatus).toBe('not-run');
  });

  it('attention-plan is conditional until published (#1945)', () => {
    const day: PipelineDayData = {
      runRecorded: true,
      fanoutCounts: {},
      fanoutKeys: {},
      presentKeys: new Set(['macro']),
      artifacts: [],
    };
    const missing = layoutPipeline(day, {
      expandedStages: new Set(['inputs']),
      expandedFanouts: new Set(),
    });
    expect(missing.nodes.find((n) => n.id === 'inputs:attention-plan')?.runStatus).toBe('not-run');

    const present = layoutPipeline(
      {
        ...day,
        presentKeys: new Set(['macro', 'attention-plan']),
      },
      {
        expandedStages: new Set(['inputs']),
        expandedFanouts: new Set(),
      },
    );
    const node = present.nodes.find((n) => n.id === 'inputs:attention-plan');
    expect(node?.documentKey).toBe('attention-plan');
    expect(node?.runStatus).toBe('persisted-artifact');
  });

  it('collapsed day does not paint portfolio/Learning stages as stage-overview', () => {
    const day: PipelineDayData = {
      fanoutCounts: {},
      fanoutKeys: {},
      presentKeys: new Set(['macro']),
      artifacts: [],
    };
    const l = layoutPipeline(day, collapsed);
    const byId = (id: string) => l.nodes.find((n) => n.id === id);
    expect(byId('inputs')?.runStatus).toBe('stage-overview');
    expect(byId('research')?.runStatus).toBe('stage-overview');
    expect(byId('selection')?.runStatus).toBe('not-run');
    expect(byId('decision')?.runStatus).toBe('not-run');
    expect(byId('learning')?.runStatus).toBe('not-run');
  });

  it('#1259: digest node resolves via digest-delta on a delta day (no plain `digest` key)', () => {
    const day: PipelineDayData = {
      fanoutCounts: {},
      fanoutKeys: {},
      presentKeys: new Set(['digest-delta', 'macro']),
      artifacts: [],
    };
    const exp: ExpansionState = {
      expandedStages: new Set(['synthesis']),
      expandedFanouts: new Set(),
    };
    const l = layoutPipeline(day, exp);
    const byId = (id: string) => l.nodes.find((n) => n.id === id);
    expect(byId('synthesis:digest')?.documentKey).toBe('digest-delta');
  });
});
