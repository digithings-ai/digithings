'use client';

import { useCallback, useEffect, useState } from 'react';
import { Minus, Plus, Maximize2, ChevronDown, ChevronRight } from 'lucide-react';
import type { PipelineDayData } from '@/lib/pipeline-graph-data';
import type { ExpansionState, LaidOutNode } from '@/lib/pipeline-layout';
import { layoutPipeline } from '@/lib/pipeline-layout';
import type { PipelineStageId } from '@/lib/pipeline-topology';
import { PIPELINE_TOPOLOGY, stageById } from '@/lib/pipeline-topology';
import PipelineNode from './PipelineNode';
import PipelineConnectors from './PipelineConnectors';
import { useCanvasCamera } from './useCanvasCamera';

export interface PipelineCanvasProps {
  day: PipelineDayData;
  initialExpansion?: ExpansionState;
  selectedNodeId?: string;
  onNodeActivate: (node: LaidOutNode) => void;
}

const DEFAULT_EXPANSION: ExpansionState = {
  expandedStages: new Set(),
  expandedFanouts: new Set(),
};

export default function PipelineCanvas({
  day,
  initialExpansion,
  selectedNodeId,
  onNodeActivate,
}: PipelineCanvasProps) {
  const [expansion, setExpansion] = useState<ExpansionState>(
    initialExpansion ?? DEFAULT_EXPANSION,
  );
  const camera = useCanvasCamera();
  const { viewportRef, layerRef } = camera;

  const layout = layoutPipeline(day, expansion);

  // Fit on mount
  useEffect(() => {
    if (!viewportRef.current) return;
    const { clientWidth, clientHeight } = viewportRef.current;
    camera.fit({ width: layout.width, height: layout.height }, { width: clientWidth, height: clientHeight });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Auto-center when expansion changes (closes mockup gap #1)
  useEffect(() => {
    if (!viewportRef.current) return;
    const { clientWidth, clientHeight } = viewportRef.current;
    camera.fit({ width: layout.width, height: layout.height }, { width: clientWidth, height: clientHeight });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [expansion]);

  const handleNodeClick = useCallback(
    (node: LaidOutNode) => {
      if (node.kind === 'stage') {
        setExpansion((prev) => {
          const next = new Set(prev.expandedStages);
          if (next.has(node.stageId)) {
            next.delete(node.stageId);
          } else {
            next.add(node.stageId);
          }
          return { ...prev, expandedStages: next };
        });
        return;
      }

      if (node.kind === 'substep') {
        const subStepId = node.id.split(':')[1];
        const hasFanout = !!stageById(node.stageId)?.subSteps.find((s) => s.id === subStepId)?.fanout;
        if (hasFanout) {
          const fanoutKey = `${node.stageId}:${subStepId}`;
          setExpansion((prev) => {
            const next = new Set(prev.expandedFanouts);
            if (next.has(fanoutKey)) {
              next.delete(fanoutKey);
            } else {
              next.add(fanoutKey);
            }
            return { ...prev, expandedFanouts: next };
          });
          return;
        }
        // Leaf sub-step: open its document when one is present.
        if (node.documentKey) onNodeActivate(node);
        return;
      }

      // fanout-branch
      if (node.documentKey) onNodeActivate(node);
    },
    [onNodeActivate],
  );

  const handleFitClick = useCallback(() => {
    if (!viewportRef.current) return;
    const { clientWidth, clientHeight } = viewportRef.current;
    camera.fit({ width: layout.width, height: layout.height }, { width: clientWidth, height: clientHeight });
  }, [camera, layout, viewportRef]);

  const handleExpandAll = useCallback(() => {
    const allStages = new Set<PipelineStageId>(['inputs', 'research', 'synthesis', 'selection', 'decision']);
    const allFanouts = new Set<string>();
    for (const stage of PIPELINE_TOPOLOGY) {
      for (const sub of stage.subSteps) {
        if (sub.fanout) allFanouts.add(`${stage.id}:${sub.id}`);
      }
    }
    setExpansion({ expandedStages: allStages, expandedFanouts: allFanouts });
  }, []);

  const handleCollapseAll = useCallback(() => {
    setExpansion({ expandedStages: new Set(), expandedFanouts: new Set() });
  }, []);

  const { transform, zoomIn, zoomOut, bind } = camera;

  return (
    <div className="flex flex-col flex-1 min-h-0 min-w-0">
      {/* Toolbar */}
      <div className="flex items-center gap-2 px-6 py-2 border-b border-border text-sm text-muted flex-wrap">
        <div className="flex gap-0.5 bg-[var(--panel)] border border-border rounded-[9px] p-0.5">
          <button
            type="button"
            data-no-pan=""
            aria-label="Zoom out"
            onClick={zoomOut}
            className="h-7 w-7 flex items-center justify-center rounded-md text-muted hover:text-foreground hover:bg-white/6"
          >
            <Minus size={14} />
          </button>
          <button
            type="button"
            data-no-pan=""
            aria-label="Fit to view"
            onClick={handleFitClick}
            className="h-7 px-2.5 text-[12px] font-semibold rounded-md text-muted hover:text-foreground hover:bg-white/6"
          >
            Fit
          </button>
          <button
            type="button"
            data-no-pan=""
            aria-label="Zoom in"
            onClick={zoomIn}
            className="h-7 w-7 flex items-center justify-center rounded-md text-muted hover:text-foreground hover:bg-white/6"
          >
            <Plus size={14} />
          </button>
        </div>

        <button
          type="button"
          data-no-pan=""
          onClick={handleExpandAll}
          className="h-8 px-3 text-[12px] font-semibold rounded-[9px] border border-border bg-[var(--panel)] text-muted hover:text-foreground flex items-center gap-1.5"
        >
          <ChevronDown size={13} />
          Expand all
        </button>

        <button
          type="button"
          data-no-pan=""
          onClick={handleCollapseAll}
          className="h-8 px-3 text-[12px] font-semibold rounded-[9px] border border-border bg-[var(--panel)] text-muted hover:text-foreground flex items-center gap-1.5"
        >
          <ChevronRight size={13} />
          Collapse
        </button>

        <span className="text-[11px] text-muted ml-auto hidden sm:block">
          drag to pan · scroll to zoom · click a node to open / expand
        </span>

        <div className="flex gap-3 flex-wrap">
          <span className="flex items-center gap-1.5 text-[11px] text-muted">
            <span className="text-fin-blue text-[13px]">→</span> sequential
          </span>
          <span className="flex items-center gap-1.5 text-[11px] text-muted">
            <span className="text-fin-blue text-[13px]">↓</span> parallel
          </span>
        </div>
      </div>

      {/* Canvas viewport — overflow-hidden prevents page horizontal scroll.
          touch-action:none + overscroll-behavior:contain stop the browser from
          claiming the gesture; wheel is handled via a native passive:false
          listener inside the camera hook (not a React onWheel bind). */}
      <div
        ref={viewportRef}
        className="flex-1 min-h-0 overflow-hidden relative cursor-grab active:cursor-grabbing select-none"
        style={{ touchAction: 'none', overscrollBehavior: 'contain' }}
        {...bind}
      >
        <div
          ref={layerRef}
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            transformOrigin: '0 0',
            willChange: 'transform',
            transform: `translate3d(${transform.x}px,${transform.y}px,0) scale(${transform.scale})`,
            padding: 30,
          }}
        >
          {/* SVG connector layer */}
          <PipelineConnectors
            connectors={layout.connectors}
            nodes={layout.nodes}
            width={layout.width + 60}
            height={layout.height + 60}
          />

          {/* Node layer */}
          {layout.nodes.map((node) => {
            const isStage = node.kind === 'stage';
            const subStepId = node.kind === 'substep' ? node.id.split(':')[1] : undefined;
            // Fan-out parent identity comes from the STATIC topology, so the
            // chevron + count badge are discoverable even before data loads.
            const fanout = subStepId
              ? stageById(node.stageId)?.subSteps.find((s) => s.id === subStepId)?.fanout
              : undefined;
            const isFanoutParent = !!fanout;

            const expandable = isStage || isFanoutParent;
            const expanded = isStage
              ? expansion.expandedStages.has(node.stageId)
              : expansion.expandedFanouts.has(`${node.stageId}:${subStepId}`);

            // Count badge: live count if present, else the topology default.
            // Guard with > 0 so default-0 fan-outs don't render a noisy '0'.
            let count: number | undefined;
            if (fanout && subStepId) {
              const c = day.fanoutCounts[fanout.id] ?? fanout.defaultCount;
              if (c > 0) count = c;
            }

            // PipelineClient passes selectedNodeId = active document_key, so a
            // node is selected by its documentKey, not its layout id.
            const selected = !!node.documentKey && node.documentKey === selectedNodeId;

            return (
              <PipelineNode
                key={node.id}
                node={node}
                count={count}
                expandable={expandable}
                expanded={expanded}
                selected={selected}
                onActivate={() => handleNodeClick(node)}
              />
            );
          })}
        </div>
      </div>
    </div>
  );
}
