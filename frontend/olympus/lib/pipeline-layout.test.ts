import { describe, it, expect } from 'vitest';
import { layoutPipeline } from './pipeline-layout';
import type { ExpansionState } from './pipeline-layout';
import type { PipelineDayData } from './pipeline-graph-data';

const emptyDay: PipelineDayData = { fanoutCounts: { sectors: 12 }, presentKeys: new Set<string>() };
const collapsed: ExpansionState = { expandedStages: new Set(), expandedFanouts: new Set() };

describe('layoutPipeline', () => {
  it('collapsed: five stage nodes left to right, same row', () => {
    const l = layoutPipeline(emptyDay, collapsed);
    const stages = l.nodes.filter((n) => n.kind === 'stage');
    expect(stages).toHaveLength(5);
    const xs = stages.map((n) => n.x);
    expect([...xs]).toEqual([...xs].sort((a, b) => a - b)); // strictly increasing order preserved
    expect(new Set(stages.map((n) => n.y)).size).toBe(1);   // one row
  });
  it('expanding sectors fan-out emits 12 vertical branch nodes', () => {
    const exp: ExpansionState = {
      expandedStages: new Set(['research']),
      expandedFanouts: new Set(['research:sectors']),
    };
    const l = layoutPipeline(emptyDay, exp);
    const branches = l.nodes.filter((n) => n.kind === 'fanout-branch' && n.id.startsWith('research:sectors:'));
    expect(branches).toHaveLength(12);
    const ys = branches.map((n) => n.y);
    expect(new Set(branches.map((n) => n.x)).size).toBe(1); // same column
    expect([...ys]).toEqual([...ys].sort((a, b) => a - b)); // stacked downward
  });
});
