/**
 * Honest runtime status for every static PIPELINE_TOPOLOGY node (#2631 / #1945).
 *
 * Never paint active/success chrome for a stage or sub-step the run did not
 * reach. Atlas (inputs→synthesis), Hermes (selection→decision), and Learning
 * are separate bands: research artifacts do not imply Hermes ran.
 */

import type { PipelineDayData } from './pipeline-graph-data';
import { leafDocumentKey, resolvePresentDigestKey, stageForDocumentKey } from './pipeline-links';
import { PIPELINE_TOPOLOGY, type PipelineStageId, type StageDef, type SubStep } from './pipeline-topology';

export type PipelineNodeRunStatus =
  | 'stage-overview'
  | 'not-run'
  | 'state-only'
  | 'persisted-artifact'
  | 'expected-artifact-missing'
  | 'parallel-dispatch';

export function pipelineNodeRunStatusLabel(status: PipelineNodeRunStatus): string {
  if (status === 'stage-overview') return 'Stage overview';
  if (status === 'not-run') return 'Not run';
  if (status === 'state-only') return 'State-only operation';
  if (status === 'persisted-artifact') return 'Persisted artifact';
  if (status === 'expected-artifact-missing') return 'Expected artifact missing';
  return 'Parallel dispatch';
}

const ATLAS_STAGES = new Set<PipelineStageId>(['inputs', 'research', 'synthesis']);
const HERMES_STAGES = new Set<PipelineStageId>(['selection', 'decision']);

export type TopologyBand = 'atlas' | 'hermes' | 'learning';

export function topologyBand(stageId: PipelineStageId): TopologyBand {
  if (ATLAS_STAGES.has(stageId)) return 'atlas';
  if (HERMES_STAGES.has(stageId)) return 'hermes';
  return 'learning';
}

/** Newest present commit-run key, or undefined. */
export function resolvePresentCommitKey(day: PipelineDayData): string | undefined {
  const runId = (k: string) => Number.parseInt(k.slice('commit-run/'.length), 10);
  const runs = [...day.presentKeys]
    .filter((k) => k.startsWith('commit-run/'))
    .sort((a, b) => {
      const na = runId(a);
      const nb = runId(b);
      if (Number.isNaN(na) || Number.isNaN(nb)) return a.localeCompare(b);
      return na - nb;
    });
  return runs.length > 0 ? runs[runs.length - 1] : undefined;
}

/**
 * Resolve a leaf sub-step's document_key only when it is present today
 * (golden rule). Shared with layout so status + documentKey stay aligned.
 */
export function resolveLeafDocumentKey(subStepId: string, day: PipelineDayData): string | undefined {
  if (subStepId === 'commit') return resolvePresentCommitKey(day);
  if (subStepId === 'digest') return resolvePresentDigestKey(day);
  const key = leafDocumentKey(subStepId);
  return key && day.presentKeys.has(key) ? key : undefined;
}

function stageLocalEvidence(stage: StageDef, day: PipelineDayData): boolean {
  for (const sub of stage.subSteps) {
    if (sub.stateOnly) continue;
    if (sub.fanout) {
      if ((day.fanoutKeys[sub.fanout.id] ?? []).length > 0) return true;
      continue;
    }
    if (resolveLeafDocumentKey(sub.id, day)) return true;
  }
  return false;
}

export interface TopologyEvidenceBands {
  runRecorded: boolean;
  /** Snapshot-only day: Atlas-only reach; Hermes/Learning stay not-run. */
  emptyRecordedRun: boolean;
  atlas: boolean;
  hermes: boolean;
  learning: boolean;
}

/** Classify which pipeline bands have evidence on this day. */
export function topologyEvidenceBands(day: PipelineDayData): TopologyEvidenceBands {
  const runRecorded = day.runRecorded ?? day.presentKeys.size > 0;
  const emptyRecordedRun = runRecorded && day.presentKeys.size === 0;

  let atlas = false;
  let hermes = false;
  let learning = false;

  for (const key of day.presentKeys) {
    const stage = stageForDocumentKey(key);
    if (!stage) continue;
    const band = topologyBand(stage);
    if (band === 'atlas') atlas = true;
    else if (band === 'hermes') hermes = true;
    else learning = true;
  }

  // Later bands imply earlier graph work completed.
  if (learning) {
    hermes = true;
    atlas = true;
  } else if (hermes) {
    atlas = true;
  }

  // Snapshot-only day (run recorded, zero documents): Atlas entry is the only
  // honest reach signal. Do not paint Hermes/Learning as "expected missing".
  if (emptyRecordedRun) {
    atlas = true;
  }

  return { runRecorded, emptyRecordedRun, atlas, hermes, learning };
}

export function bandReached(bands: TopologyEvidenceBands, stageId: PipelineStageId): boolean {
  if (!bands.runRecorded) return false;
  const band = topologyBand(stageId);
  if (band === 'atlas') return bands.atlas;
  if (band === 'hermes') return bands.hermes;
  return bands.learning;
}

export function resolveSubStepRunStatus(
  sub: SubStep,
  day: PipelineDayData,
  bands: TopologyEvidenceBands,
  stageId: PipelineStageId,
): PipelineNodeRunStatus {
  if (!bands.runRecorded) return 'not-run';
  const reached = bandReached(bands, stageId);

  if (sub.stateOnly) {
    return reached ? 'state-only' : 'not-run';
  }

  if (sub.fanout) {
    const fanoutKeys = day.fanoutKeys[sub.fanout.id] ?? [];
    if (fanoutKeys.length > 0) return 'parallel-dispatch';
    if (!reached) return 'not-run';
    // Variable-width Hermes fan-outs may honestly dispatch zero branches.
    if (sub.fanout.defaultCount === 0) return 'parallel-dispatch';
    return 'expected-artifact-missing';
  }

  const leafKey = resolveLeafDocumentKey(sub.id, day);
  if (leafKey) return 'persisted-artifact';
  if (!reached) return 'not-run';
  if (sub.conditionalArtifact) return 'not-run';
  return 'expected-artifact-missing';
}

export function resolveStageRunStatus(
  stage: StageDef,
  day: PipelineDayData,
  bands: TopologyEvidenceBands,
): PipelineNodeRunStatus {
  if (!bands.runRecorded) return 'not-run';
  // Stage overview is active chrome only when this stage has local evidence
  // or an honest in-band sub-step status — never blanket every stage.
  if (stageLocalEvidence(stage, day)) return 'stage-overview';
  if (stage.id === 'inputs' && bands.atlas) return 'stage-overview';
  if (
    bandReached(bands, stage.id)
    && stage.subSteps.some(
      (sub) => resolveSubStepRunStatus(sub, day, bands, stage.id) !== 'not-run',
    )
  ) {
    return 'stage-overview';
  }
  return 'not-run';
}

/**
 * Full static topology matrix: every stage id + every `stage:substep` id.
 * Fan-out branches are runtime-only and audited via layout tests.
 */
export function auditStaticTopologyRunStatuses(
  day: PipelineDayData,
): Record<string, PipelineNodeRunStatus> {
  const bands = topologyEvidenceBands(day);
  const out: Record<string, PipelineNodeRunStatus> = {};
  for (const stage of PIPELINE_TOPOLOGY) {
    out[stage.id] = resolveStageRunStatus(stage, day, bands);
    for (const sub of stage.subSteps) {
      out[`${stage.id}:${sub.id}`] = resolveSubStepRunStatus(sub, day, bands, stage.id);
    }
  }
  return out;
}

/** Every static topology node id (stages + sub-steps). */
export function staticTopologyNodeIds(): string[] {
  const ids: string[] = [];
  for (const stage of PIPELINE_TOPOLOGY) {
    ids.push(stage.id);
    for (const sub of stage.subSteps) {
      ids.push(`${stage.id}:${sub.id}`);
    }
  }
  return ids;
}
