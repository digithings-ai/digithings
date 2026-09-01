import { PIPELINE_TOPOLOGY } from './pipeline-topology';
import type { PipelineStageId, StageDef } from './pipeline-topology';
import type { PipelineDayData } from './pipeline-graph-data';
import {
  bandReached,
  pipelineNodeRunStatusLabel,
  resolveLeafDocumentKey,
  resolveStageRunStatus,
  resolveSubStepRunStatus,
  topologyEvidenceBands,
  type PipelineNodeRunStatus,
} from './pipeline-topology-status';

export type { PipelineNodeRunStatus };
export { pipelineNodeRunStatusLabel };

export interface LaidOutNode {
  id: string;
  kind: 'stage' | 'substep' | 'fanout-branch';
  stageId: PipelineStageId;
  label: string;
  x: number;
  y: number;
  width: number;
  height: number;
  documentKey?: string;
  /** Backend runs this step in-state only — it never publishes a document (see SubStep.stateOnly). */
  stateOnly?: boolean;
  runStatus?: PipelineNodeRunStatus;
}

export interface Connector { fromId: string; toId: string; active?: boolean; }

export interface PipelineLayout {
  nodes: LaidOutNode[];
  connectors: Connector[];
  width: number;
  height: number;
}

export interface ExpansionState {
  expandedStages: Set<PipelineStageId>;
  expandedFanouts: Set<string>;
}

const NODE_W = 160;
const NODE_H = 48;
const GAP_X = 24;
const GAP_Y = 12;
const BASE_Y = 0;

/** Derive the human-readable branch label (entity suffix) from a fan-out document_key. */
function branchLabel(fanoutId: string, documentKey: string): string {
  if (fanoutId === 'analysts' || fanoutId === 'deliberation') {
    return documentKey.split('/')[1] ?? documentKey;
  }
  if (fanoutId === 'sectors') return documentKey.replace('sector-', '');
  // asset-classes are bare names; alt-/inst- keep their full key as the label.
  return documentKey;
}

/** Decision collapses onto the booked book; commit-run stays ledger-only. */
function resolveStageDocumentKey(stage: StageDef, day: PipelineDayData): string | undefined {
  if (stage.id === 'decision' && day.presentKeys.has('pm-rebalance')) {
    return 'pm-rebalance';
  }
  return undefined;
}

export function layoutPipeline(day: PipelineDayData, expansion: ExpansionState): PipelineLayout {
  const nodes: LaidOutNode[] = [];
  const connectors: Connector[] = [];
  let cursorX = 0;
  let maxY = NODE_H;
  const bands = topologyEvidenceBands(day);
  let prevStageId: string | null = null;

  for (const stage of PIPELINE_TOPOLOGY) {
    const stageExpanded = expansion.expandedStages.has(stage.id);
    const stageNodeId = stage.id;
    const stageStatus = resolveStageRunStatus(stage, day, bands);
    const stageX = cursorX;

    const stageDocKey = resolveStageDocumentKey(stage, day);
    nodes.push({
      id: stageNodeId,
      kind: 'stage',
      stageId: stage.id,
      label: stage.label,
      x: stageX,
      y: BASE_Y,
      width: NODE_W,
      height: NODE_H,
      documentKey: stageDocKey,
      runStatus: stageDocKey ? 'persisted-artifact' : stageStatus,
    });
    if (prevStageId) connectors.push({ fromId: prevStageId, toId: stageNodeId });
    prevStageId = stageNodeId;

    let stackY = BASE_Y + NODE_H + GAP_Y;
    let prevId: string = stageNodeId;
    const visibleSubs = stage.subSteps.filter((sub) => !sub.hiddenFromGraph);

    if (stageExpanded) {
      for (const sub of visibleSubs) {
        const subId = `${stage.id}:${sub.id}`;
        const fanoutKey = `${stage.id}:${sub.id}`;
        const fanoutExpanded = expansion.expandedFanouts.has(fanoutKey);

        // Leaf sub-steps (no fan-out) carry a document_key when it's present
        // today. State-only steps never resolve one — the backend runs them
        // but publishes nothing (thesis framing, screener, consolidate, preflight).
        const leafKey =
          sub.fanout || sub.stateOnly ? undefined : resolveLeafDocumentKey(sub.id, day);
        const runStatus = resolveSubStepRunStatus(sub, day, bands, stage.id);

        nodes.push({
          id: subId,
          kind: 'substep',
          stageId: stage.id,
          label: sub.label,
          x: stageX,
          y: stackY,
          width: NODE_W,
          height: NODE_H,
          documentKey: leafKey,
          stateOnly: sub.stateOnly,
          runStatus,
        });
        connectors.push({ fromId: prevId, toId: subId, active: true });
        prevId = subId;
        stackY += NODE_H + GAP_Y;

        if (sub.fanout && fanoutExpanded) {
          const keys = day.fanoutKeys[sub.fanout.id] ?? [];
          if (keys.length > 0) {
            keys.forEach((documentKey, i) => {
              const branchId = `${stage.id}:${sub.id}:${i}`;
              nodes.push({
                id: branchId,
                kind: 'fanout-branch',
                stageId: stage.id,
                label: branchLabel(sub.fanout!.id, documentKey),
                x: stageX,
                y: stackY,
                width: NODE_W,
                height: NODE_H,
                documentKey,
                runStatus: 'persisted-artifact',
              });
              connectors.push({ fromId: prevId, toId: branchId, active: true });
              prevId = branchId;
              stackY += NODE_H + GAP_Y;
            });
          } else {
            const count = day.fanoutCounts[sub.fanout.id] ?? sub.fanout.defaultCount;
            const branchStatus: PipelineNodeRunStatus = bandReached(bands, stage.id)
              ? 'expected-artifact-missing'
              : 'not-run';
            for (let i = 0; i < count; i++) {
              const branchId = `${stage.id}:${sub.id}:${i}`;
              nodes.push({
                id: branchId,
                kind: 'fanout-branch',
                stageId: stage.id,
                label: `${sub.label} ${i + 1}`,
                x: stageX,
                y: stackY,
                width: NODE_W,
                height: NODE_H,
                runStatus: branchStatus,
              });
              connectors.push({ fromId: prevId, toId: branchId, active: true });
              prevId = branchId;
              stackY += NODE_H + GAP_Y;
            }
          }
        }
      }
    }

    if (stackY - GAP_Y > maxY) maxY = stackY - GAP_Y;
    cursorX += NODE_W + GAP_X;
  }

  if (BASE_Y + NODE_H > maxY) maxY = BASE_Y + NODE_H;

  return {
    nodes,
    connectors,
    width: cursorX,
    height: maxY,
  };
}
