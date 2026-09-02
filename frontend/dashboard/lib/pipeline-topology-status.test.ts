import { describe, it, expect } from 'vitest';
import type { PipelineDayData } from './pipeline-graph-data';
import { PIPELINE_TOPOLOGY } from './pipeline-topology';
import {
  auditStaticTopologyRunStatuses,
  pipelineNodeRunStatusLabel,
  resolvePresentCommitKey,
  staticTopologyNodeIds,
  topologyEvidenceBands,
  type PipelineNodeRunStatus,
} from './pipeline-topology-status';

const emptyDay: PipelineDayData = {
  fanoutCounts: {},
  fanoutKeys: {},
  presentKeys: new Set<string>(),
  artifacts: [],
};

const ACTIVE_STATUSES = new Set<PipelineNodeRunStatus>([
  'stage-overview',
  'state-only',
  'persisted-artifact',
  'expected-artifact-missing',
  'parallel-dispatch',
]);

describe('pipeline topology status audit', () => {
  it('enumerates every static stage and sub-step exactly once', () => {
    const ids = staticTopologyNodeIds();
    const expected: string[] = [];
    for (const stage of PIPELINE_TOPOLOGY) {
      expected.push(stage.id);
      for (const sub of stage.subSteps) expected.push(`${stage.id}:${sub.id}`);
    }
    expect(ids).toEqual(expected);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it('labels every status for Pipeline chrome', () => {
    const statuses: PipelineNodeRunStatus[] = [
      'stage-overview',
      'not-run',
      'state-only',
      'persisted-artifact',
      'expected-artifact-missing',
      'parallel-dispatch',
    ];
    for (const status of statuses) {
      expect(pipelineNodeRunStatusLabel(status).length).toBeGreaterThan(0);
    }
  });

  it('empty day: every static node is not-run (no fake green)', () => {
    const matrix = auditStaticTopologyRunStatuses(emptyDay);
    for (const id of staticTopologyNodeIds()) {
      expect(matrix[id], id).toBe('not-run');
    }
  });

  it('research-only day: Atlas honest, Hermes/Learning stay not-run', () => {
    const day: PipelineDayData = {
      fanoutCounts: { sectors: 1 },
      fanoutKeys: { sectors: ['sector-technology'] },
      presentKeys: new Set(['macro', 'sector-technology']),
      artifacts: [],
    };
    const bands = topologyEvidenceBands(day);
    expect(bands.atlas).toBe(true);
    expect(bands.hermes).toBe(false);
    expect(bands.learning).toBe(false);

    const matrix = auditStaticTopologyRunStatuses(day);
    expect(matrix.inputs).toBe('stage-overview');
    expect(matrix['inputs:preflight']).toBe('expected-artifact-missing');
    expect(matrix['inputs:attention-plan']).toBe('not-run');
    expect(matrix.research).toBe('stage-overview');
    expect(matrix['research:macro']).toBe('persisted-artifact');
    expect(matrix['research:sectors']).toBe('parallel-dispatch');
    expect(matrix['research:alt-data']).toBe('expected-artifact-missing');
    expect(matrix['research:scorecard']).toBeUndefined();
    expect(matrix.synthesis).toBe('stage-overview');
    expect(matrix['synthesis:consolidate']).toBe('expected-artifact-missing');
    expect(matrix['synthesis:digest']).toBe('expected-artifact-missing');
    expect(matrix.selection).toBe('not-run');
    expect(matrix['selection:thesis']).toBe('not-run');
    expect(matrix['selection:analysts']).toBe('not-run');
    expect(matrix.decision).toBe('not-run');
    expect(matrix['decision:commit']).toBe('not-run');
    expect(matrix.learning).toBe('not-run');
    expect(matrix['learning:beliefs']).toBe('not-run');

    for (const id of ['selection', 'selection:thesis', 'selection:analysts', 'decision', 'learning']) {
      expect(ACTIVE_STATUSES.has(matrix[id]!), id).toBe(false);
    }
  });

  it('Hermes commit implies Learning should have published a same-date beliefs doc (WP-I)', () => {
    const day: PipelineDayData = {
      fanoutCounts: {},
      fanoutKeys: {
        analysts: ['analyst/QQQ'],
        deliberation: ['deliberation/QQQ'],
      },
      presentKeys: new Set([
        'macro',
        'digest',
        'analyst/QQQ',
        'deliberation/QQQ',
        'pm-direction-memo',
        'pm-rebalance',
        'commit-run/42',
      ]),
      artifacts: [],
    };
    const matrix = auditStaticTopologyRunStatuses(day);
    expect(matrix.inputs).toBe('stage-overview');
    expect(matrix.research).toBe('stage-overview');
    expect(matrix.synthesis).toBe('stage-overview');
    expect(matrix['synthesis:digest']).toBe('persisted-artifact');
    expect(matrix.selection).toBe('stage-overview');
    expect(matrix['selection:thesis']).toBe('expected-artifact-missing');
    expect(matrix['selection:analysts']).toBe('parallel-dispatch');
    expect(matrix['selection:pm-direction']).toBe('persisted-artifact');
    expect(matrix.decision).toBe('stage-overview');
    expect(matrix['decision:commit']).toBe('persisted-artifact');
    expect(matrix.learning).toBe('stage-overview');
    expect(matrix['learning:beliefs']).toBe('expected-artifact-missing');
  });

  it('recorded run with zero documents: Atlas-only reach; Hermes/Learning stay not-run', () => {
    const day: PipelineDayData = { ...emptyDay, runRecorded: true };
    const bands = topologyEvidenceBands(day);
    expect(bands.emptyRecordedRun).toBe(true);
    expect(bands.atlas).toBe(true);
    expect(bands.hermes).toBe(false);
    expect(bands.learning).toBe(false);

    const matrix = auditStaticTopologyRunStatuses(day);
    expect(matrix['inputs:preflight']).toBe('expected-artifact-missing');
    expect(matrix['inputs:attention-plan']).toBe('not-run');
    expect(matrix['synthesis:consolidate']).toBe('expected-artifact-missing');
    expect(matrix['synthesis:digest']).toBe('expected-artifact-missing');
    expect(matrix.selection).toBe('not-run');
    expect(matrix['selection:analysts']).toBe('not-run');
    expect(matrix['decision:commit']).toBe('not-run');
    expect(matrix.learning).toBe('not-run');
    expect(matrix['learning:beliefs']).toBe('not-run');
  });

  it('covers every static node id in the audit map', () => {
    const matrix = auditStaticTopologyRunStatuses({
      ...emptyDay,
      presentKeys: new Set(['macro']),
    });
    for (const id of staticTopologyNodeIds()) {
      expect(matrix[id], id).toBeDefined();
    }
  });

  it('commit-run keys stay ledger-internal: newest numeric run_id still resolves', () => {
    const day: PipelineDayData = {
      fanoutCounts: {},
      fanoutKeys: {},
      presentKeys: new Set(['commit-run/9999999999', 'commit-run/10000000000']),
      artifacts: [],
    };
    expect(resolvePresentCommitKey(day)).toBe('commit-run/10000000000');
  });
});
