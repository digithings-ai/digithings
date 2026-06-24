import { PIPELINE_TOPOLOGY } from './pipeline-topology';
import type { PipelineStageId } from './pipeline-topology';
import type { PipelineDayData } from './pipeline-graph-data';

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

export interface Connector { fromId: string; toId: string; }

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

        nodes.push({
          id: subId,
          kind: 'substep',
          stageId: stage.id,
          label: sub.label,
          x: subX,
          y: BASE_Y,
          width: NODE_W,
          height: NODE_H,
        });
        if (prevId) connectors.push({ fromId: prevId, toId: subId });
        prevId = subId;
        cursorX += NODE_W + GAP_X;

        if (sub.fanout && fanoutExpanded) {
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
            connectors.push({ fromId: subId, toId: branchId });
            if (branchY + NODE_H > maxY) maxY = branchY + NODE_H;
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
