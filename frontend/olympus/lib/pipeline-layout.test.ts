import { describe, it, expect } from 'vitest';
import { layoutPipeline } from './pipeline-layout';
import type { ExpansionState } from './pipeline-layout';
import type { PipelineDayData } from './pipeline-graph-data';

const emptyDay: PipelineDayData = {
  fanoutCounts: { sectors: 11 },
  fanoutKeys: {},
  presentKeys: new Set<string>(),
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
      presentKeys: new Set(['macro', 'pm-direction-memo', 'sector-scorecard', 'beliefs', 'commit-run/123', 'commit-run/999']),
    };
    const exp: ExpansionState = {
      expandedStages: new Set(['research', 'synthesis', 'selection', 'decision', 'learning']),
      expandedFanouts: new Set(),
    };
    const l = layoutPipeline(day, exp);
    const byId = (id: string) => l.nodes.find((n) => n.id === id);

    expect(byId('research:macro')?.documentKey).toBe('macro');
    expect(byId('selection:pm-direction')?.documentKey).toBe('pm-direction-memo');
    // digest absent that day -> no documentKey (golden rule)
    expect(byId('synthesis:digest')?.documentKey).toBeUndefined();
    // sector-scorecard is a research leaf (Phase-5 equities output, #1538)
    expect(byId('research:scorecard')?.documentKey).toBe('sector-scorecard');
    // consolidate is state-only: never keyed, even when scorecard is present
    expect(byId('synthesis:consolidate')?.documentKey).toBeUndefined();
    expect(byId('synthesis:consolidate')?.stateOnly).toBe(true);
    // beliefs fold resolves when the on-demand doc is present (#1383)
    expect(byId('learning:beliefs')?.documentKey).toBe('beliefs');
    // commit resolves via a present commit-run/* (numerically-newest run_id)
    expect(byId('decision:commit')?.documentKey).toBe('commit-run/999');
    // thesis/screener are state-only: never keyed
    expect(byId('selection:thesis')?.documentKey).toBeUndefined();
    expect(byId('selection:thesis')?.stateOnly).toBe(true);
    expect(byId('selection:screener')?.documentKey).toBeUndefined();
  });

  it('commit picks the numerically-newest run_id across digit-length boundaries (#1538)', () => {
    const day: PipelineDayData = {
      fanoutCounts: {},
      fanoutKeys: {},
      // Lexicographically '9999999999' > '10000000000' — numerically the reverse.
      presentKeys: new Set(['commit-run/9999999999', 'commit-run/10000000000']),
    };
    const exp: ExpansionState = {
      expandedStages: new Set(['decision']),
      expandedFanouts: new Set(),
    };
    const l = layoutPipeline(day, exp);
    const commit = l.nodes.find((n) => n.id === 'decision:commit');
    expect(commit?.documentKey).toBe('commit-run/10000000000');
  });

  it('beliefs node is inert (no documentKey) on non-trigger days', () => {
    const day: PipelineDayData = {
      fanoutCounts: {},
      fanoutKeys: {},
      presentKeys: new Set(['macro']),
    };
    const exp: ExpansionState = {
      expandedStages: new Set(['learning']),
      expandedFanouts: new Set(),
    };
    const l = layoutPipeline(day, exp);
    expect(l.nodes.find((n) => n.id === 'learning:beliefs')?.documentKey).toBeUndefined();
  });

  it('#1259: digest node resolves via digest-delta on a delta day (no plain `digest` key)', () => {
    const day: PipelineDayData = {
      fanoutCounts: {},
      fanoutKeys: {},
      presentKeys: new Set(['digest-delta', 'macro']),
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
