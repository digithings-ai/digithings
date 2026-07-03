import { describe, it, expect } from 'vitest';
import { layoutPipeline } from './pipeline-layout';
import type { ExpansionState } from './pipeline-layout';
import type { PipelineDayData } from './pipeline-graph-data';

const emptyDay: PipelineDayData = {
  fanoutCounts: { sectors: 12 },
  fanoutKeys: {},
  presentKeys: new Set<string>(),
};
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

  it('expanding sectors fan-out (no fanoutKeys) falls back to count-indexed branches with NO documentKey', () => {
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
      presentKeys: new Set(['macro', 'pm-direction-memo', 'commit-run/123', 'commit-run/999']),
    };
    const exp: ExpansionState = {
      expandedStages: new Set(['research', 'synthesis', 'selection', 'decision']),
      expandedFanouts: new Set(),
    };
    const l = layoutPipeline(day, exp);
    const byId = (id: string) => l.nodes.find((n) => n.id === id);

    expect(byId('research:macro')?.documentKey).toBe('macro');
    expect(byId('selection:pm-direction')?.documentKey).toBe('pm-direction-memo');
    // digest absent that day -> no documentKey (golden rule)
    expect(byId('synthesis:digest')?.documentKey).toBeUndefined();
    // consolidate maps to sector-scorecard, absent -> undefined
    expect(byId('synthesis:consolidate')?.documentKey).toBeUndefined();
    // commit resolves via a present commit-run/* (lexicographically-last default)
    expect(byId('decision:commit')?.documentKey).toBe('commit-run/999');
    // thesis/screener never get a key
    expect(byId('selection:thesis')?.documentKey).toBeUndefined();
    expect(byId('selection:screener')?.documentKey).toBeUndefined();
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
