import { PIPELINE_TOPOLOGY } from './pipeline-topology';
import type { PipelineStageId } from './pipeline-topology';
import type { PipelineDayData } from './pipeline-graph-data';
import { leafDocumentKey } from './pipeline-links';

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

/**
 * Resolve a leaf sub-step's document_key, honouring the golden rule: only
 * return a key that is actually present in this day's documents. `commit` is
 * special-cased — there can be several `commit-run/{run_id}` keys per day, so
 * we pick the present ones and default to the lexicographically-last.
 */
function resolveLeafDocumentKey(subStepId: string, day: PipelineDayData): string | undefined {
  if (subStepId === 'commit') {
    const runs = [...day.presentKeys].filter((k) => k.startsWith('commit-run/')).sort();
    return runs.length > 0 ? runs[runs.length - 1] : undefined;
  }
  const key = leafDocumentKey(subStepId);
  return key && day.presentKeys.has(key) ? key : undefined;
}

/** Derive the human-readable branch label (entity suffix) from a fan-out document_key. */
function branchLabel(fanoutId: string, documentKey: string): string {
  if (fanoutId === 'analysts' || fanoutId === 'deliberation') {
    return documentKey.split('/')[1] ?? documentKey;
  }
  if (fanoutId === 'sectors') return documentKey.replace('sector-', '');
  // asset-classes are bare names; alt-/inst- keep their full key as the label.
  return documentKey;
}

export function layoutPipeline(day: PipelineDayData, expansion: ExpansionState): PipelineLayout {
  const nodes: LaidOutNode[] = [];
  const connectors: Connector[] = [];
  let cursorX = 0;
  let maxY = NODE_H;

  for (const stage of PIPELINE_TOPOLOGY) {
    const stageExpanded = expansion.expandedStages.has(stage.id);
    const stageNodeId = stage.id;

    if (!stageExpanded) {
      nodes.push({
        id: stageNodeId,
        kind: 'stage',
        stageId: stage.id,
        label: stage.label,
        x: cursorX,
        y: BASE_Y,
        width: NODE_W,
        height: NODE_H,
      });
      if (nodes.length > 1) {
        connectors.push({ fromId: nodes[nodes.length - 2].id, toId: stageNodeId });
      }
      cursorX += NODE_W + GAP_X;
    } else {
      // Stage is expanded: emit sub-steps inline
      const stageStartX = cursorX;
      let prevId: string | null = null;

      // Stage header node
      nodes.push({
        id: stageNodeId,
        kind: 'stage',
        stageId: stage.id,
        label: stage.label,
        x: cursorX,
        y: BASE_Y,
        width: NODE_W,
        height: NODE_H,
      });
      if (nodes.length > 1) {
        const prevStageNode = nodes.find(
          (n) => n.kind === 'stage' && n.stageId !== stage.id && n.x < stageStartX,
        );
        if (prevStageNode) connectors.push({ fromId: prevStageNode.id, toId: stageNodeId });
      }
      prevId = stageNodeId;
      cursorX += NODE_W + GAP_X;

      for (const sub of stage.subSteps) {
        const subId = `${stage.id}:${sub.id}`;
        const fanoutKey = `${stage.id}:${sub.id}`;
        const fanoutExpanded = expansion.expandedFanouts.has(fanoutKey);
        const subX = cursorX;

        // Leaf sub-steps (no fan-out) carry a document_key when it's present today.
        const leafKey = sub.fanout ? undefined : resolveLeafDocumentKey(sub.id, day);

        nodes.push({
          id: subId,
          kind: 'substep',
          stageId: stage.id,
          label: sub.label,
          x: subX,
          y: BASE_Y,
          width: NODE_W,
          height: NODE_H,
          documentKey: leafKey,
        });
        // Sequential connectors inside an expanded stage are "active" (the
        // expanded stage's own internal flow), so they read in cyan on top.
        if (prevId) connectors.push({ fromId: prevId, toId: subId, active: true });
        prevId = subId;
        cursorX += NODE_W + GAP_X;

        if (sub.fanout && fanoutExpanded) {
          const keys = day.fanoutKeys[sub.fanout.id] ?? [];
          if (keys.length > 0) {
            // Emit one branch per real document_key, clickable.
            keys.forEach((documentKey, i) => {
              const branchId = `${stage.id}:${sub.id}:${i}`;
              const branchY = BASE_Y + (i + 1) * (NODE_H + GAP_Y);
              nodes.push({
                id: branchId,
                kind: 'fanout-branch',
                stageId: stage.id,
                label: branchLabel(sub.fanout!.id, documentKey),
                x: subX,
                y: branchY,
                width: NODE_W,
                height: NODE_H,
                documentKey,
              });
              // Fan-out branch connectors flow out of an expanded fan-out.
              connectors.push({ fromId: subId, toId: branchId, active: true });
              if (branchY + NODE_H > maxY) maxY = branchY + NODE_H;
            });
          } else {
            // No-data fallback: index-emit placeholder branches with NO documentKey
            // (renders the shape but is not clickable) so nothing regresses.
            const count = day.fanoutCounts[sub.fanout.id] ?? sub.fanout.defaultCount;
            for (let i = 0; i < count; i++) {
              const branchId = `${stage.id}:${sub.id}:${i}`;
              const branchY = BASE_Y + (i + 1) * (NODE_H + GAP_Y);
              nodes.push({
                id: branchId,
                kind: 'fanout-branch',
                stageId: stage.id,
                label: `${sub.label} ${i + 1}`,
                x: subX,
                y: branchY,
                width: NODE_W,
                height: NODE_H,
              });
              connectors.push({ fromId: subId, toId: branchId, active: true });
              if (branchY + NODE_H > maxY) maxY = branchY + NODE_H;
            }
          }
        }
      }
    }
  }

  if (BASE_Y + NODE_H > maxY) maxY = BASE_Y + NODE_H;

  return {
    nodes,
    connectors,
    width: cursorX,
    height: maxY,
  };
}
