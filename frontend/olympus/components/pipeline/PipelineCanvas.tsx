'use client';

import { useCallback, useEffect, useState } from 'react';
import { ChevronDown, ChevronLeft, ChevronRight, Minus, Plus } from 'lucide-react';
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

export function movePipelineStage(index: number, direction: -1 | 1): number {
  return Math.max(0, Math.min(PIPELINE_TOPOLOGY.length - 1, index + direction));
}

export default function PipelineCanvas({
  day,
  initialExpansion,
  selectedNodeId,
  onNodeActivate,
}: PipelineCanvasProps) {
  const [expansion, setExpansion] = useState<ExpansionState>(
    initialExpansion ?? DEFAULT_EXPANSION,
  );
  const [mobileStageIndex, setMobileStageIndex] = useState(() => {
    const initialStage = initialExpansion?.expandedStages.values().next().value;
    const index = PIPELINE_TOPOLOGY.findIndex((stage) => stage.id === initialStage);
    return index >= 0 ? index : 0;
  });
  const camera = useCanvasCamera();
  const { viewportRef, layerRef, fit } = camera;

  const layout = layoutPipeline(day, expansion);
  const mobileStage = PIPELINE_TOPOLOGY[mobileStageIndex];
  const mobileExpansion: ExpansionState = {
    expandedStages: new Set([mobileStage.id]),
    expandedFanouts: expansion.expandedFanouts,
  };
  const mobileNodes = layoutPipeline(day, mobileExpansion).nodes.filter(
    (node) => node.stageId === mobileStage.id && node.kind !== 'stage',
  );

  const fitToViewport = useCallback(() => {
    const viewport = viewportRef.current;
    if (!viewport || viewport.clientWidth <= 0 || viewport.clientHeight <= 0) return;
    fit(
      { width: layout.width, height: layout.height },
      { width: viewport.clientWidth, height: viewport.clientHeight },
    );
  }, [fit, layout.height, layout.width, viewportRef]);

  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;

    let frame: number | null = null;
    const scheduleFit = () => {
      if (frame !== null) cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        frame = null;
        fitToViewport();
      });
    };

    const observer = new ResizeObserver(scheduleFit);
    observer.observe(viewport);
    scheduleFit();

    return () => {
      observer.disconnect();
      if (frame !== null) cancelAnimationFrame(frame);
    };
  }, [fitToViewport, viewportRef]);

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
    fitToViewport();
  }, [fitToViewport]);

  const handleExpandAll = useCallback(() => {
    // Derive from the topology — a hardcoded list silently dropped the
    // `learning` stage when #1538 added it (#1553).
    const allStages = new Set<PipelineStageId>(PIPELINE_TOPOLOGY.map((s) => s.id));
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
      <div className="flex min-h-0 flex-1 flex-col md:hidden">
        <div className="border-y border-hair bg-surface px-4 py-3">
          <div className="flex items-center gap-3">
            <button
              type="button"
              aria-label="Previous pipeline section"
              disabled={mobileStageIndex === 0}
              onClick={() => setMobileStageIndex((index) => movePipelineStage(index, -1))}
              className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-hair text-ink transition-colors hover:border-accent/50 hover:text-accent disabled:cursor-not-allowed disabled:opacity-30"
            >
              <ChevronLeft size={20} aria-hidden />
            </button>
            <div className="min-w-0 flex-1 text-center">
              <span className="block font-mono text-[0.6rem] uppercase tracking-[0.1em] text-ink-mute">
                Stage {mobileStageIndex + 1} of {PIPELINE_TOPOLOGY.length}
              </span>
              <span className="mt-0.5 block truncate font-display text-xl text-ink">
                {mobileStage.label}
              </span>
            </div>
            <button
              type="button"
              aria-label="Next pipeline section"
              disabled={mobileStageIndex === PIPELINE_TOPOLOGY.length - 1}
              onClick={() => setMobileStageIndex((index) => movePipelineStage(index, 1))}
              className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-hair text-ink transition-colors hover:border-accent/50 hover:text-accent disabled:cursor-not-allowed disabled:opacity-30"
            >
              <ChevronRight size={20} aria-hidden />
            </button>
          </div>
          <div className="mt-3 grid grid-cols-6 gap-1" aria-hidden>
            {PIPELINE_TOPOLOGY.map((stage, index) => (
              <span
                key={stage.id}
                className={`h-1 rounded-full ${index === mobileStageIndex ? 'bg-accent' : 'bg-hair'}`}
              />
            ))}
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
          <div className="border-l border-hair pl-3">
            {mobileNodes.map((node) => {
              const subStepId = node.kind === 'substep' ? node.id.split(':')[1] : undefined;
              const fanout = subStepId
                ? stageById(node.stageId)?.subSteps.find((step) => step.id === subStepId)?.fanout
                : undefined;
              const fanoutKey = subStepId ? `${node.stageId}:${subStepId}` : '';
              const expandable = Boolean(fanout);
              const expanded = expandable && expansion.expandedFanouts.has(fanoutKey);
              const isInert = !expandable && !node.documentKey;
              const count = fanout
                ? day.fanoutCounts[fanout.id] ?? fanout.defaultCount
                : undefined;
              const selected = Boolean(
                node.documentKey && node.documentKey === selectedNodeId,
              );

              return (
                <button
                  key={node.id}
                  type="button"
                  disabled={isInert}
                  aria-expanded={expandable ? expanded : undefined}
                  aria-current={selected ? 'step' : undefined}
                  onClick={() => handleNodeClick(node)}
                  className={`mb-2 flex min-h-14 w-full items-center gap-3 rounded-lg border px-3 py-2.5 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60 ${
                    node.kind === 'fanout-branch'
                      ? 'ml-4 w-[calc(100%-1rem)] border-hair bg-term-bg'
                      : 'border-hair bg-surface'
                  } ${
                    isInert
                      ? 'cursor-default opacity-55'
                      : 'hover:border-accent/50 hover:bg-accent/[0.04]'
                  } ${selected ? 'border-accent/60 shadow-[0_0_0_1px_var(--accent)]' : ''}`}
                >
                  <span
                    className={`h-2.5 w-2.5 shrink-0 rounded-full ${
                      node.documentKey || (expandable && count && count > 0)
                        ? 'bg-accent'
                        : 'bg-hair'
                    }`}
                    aria-hidden
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block font-mono text-xs text-ink">
                      {node.label}
                    </span>
                    {isInert ? (
                      <span className="mt-0.5 block text-[0.68rem] text-ink-mute">
                        {node.stateOnly ? 'Runs in pipeline state only' : 'No output for this day'}
                      </span>
                    ) : null}
                  </span>
                  {count != null && count > 0 ? (
                    <span className="rounded-full bg-accent/15 px-2 py-0.5 font-mono text-[0.65rem] tabular-nums text-accent">
                      {count}
                    </span>
                  ) : null}
                  {expandable ? (
                    expanded ? <ChevronDown size={16} aria-hidden /> : <ChevronRight size={16} aria-hidden />
                  ) : node.documentKey ? (
                    <span className="font-mono text-[0.62rem] uppercase tracking-[0.08em] text-accent">
                      Open
                    </span>
                  ) : null}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      <div className="hidden min-h-0 min-w-0 flex-1 flex-col md:flex">
        {/* Toolbar */}
        <div className="flex items-center gap-2 px-6 py-2 border-b border-hair text-sm text-ink-mute flex-wrap">
          <div className="flex gap-0.5 bg-term-bg border border-hair rounded-[9px] p-0.5">
          <button
            type="button"
            data-no-pan=""
            aria-label="Zoom out"
            onClick={zoomOut}
            className="h-7 w-7 flex items-center justify-center rounded-md text-ink-mute hover:text-ink hover:bg-accent/10"
          >
            <Minus size={14} />
          </button>
          <button
            type="button"
            data-no-pan=""
            aria-label="Fit to view"
            onClick={handleFitClick}
            className="h-7 px-2.5 text-[12px] font-medium rounded-md text-ink-mute hover:text-ink hover:bg-accent/10"
          >
            Fit
          </button>
          <button
            type="button"
            data-no-pan=""
            aria-label="Zoom in"
            onClick={zoomIn}
            className="h-7 w-7 flex items-center justify-center rounded-md text-ink-mute hover:text-ink hover:bg-accent/10"
          >
            <Plus size={14} />
          </button>
        </div>

        <button
          type="button"
          data-no-pan=""
          onClick={handleExpandAll}
          className="h-8 px-3 text-[12px] font-medium rounded-[9px] border border-hair bg-term-bg text-ink-mute hover:text-ink hover:bg-accent/10 flex items-center gap-1.5"
        >
          <ChevronDown size={13} />
          Expand all
        </button>

        <button
          type="button"
          data-no-pan=""
          onClick={handleCollapseAll}
          className="h-8 px-3 text-[12px] font-medium rounded-[9px] border border-hair bg-term-bg text-ink-mute hover:text-ink hover:bg-accent/10 flex items-center gap-1.5"
        >
          <ChevronRight size={13} />
          Collapse
        </button>

          <span className="text-[11px] text-ink-mute ml-auto hidden sm:block">
            drag to pan · scroll to zoom · click a node to open / expand
          </span>

        <div className="flex gap-3 flex-wrap">
          <span className="flex items-center gap-1.5 text-[11px] text-ink-mute">
            <span className="text-accent text-[13px]">→</span> sequential
          </span>
          <span className="flex items-center gap-1.5 text-[11px] text-ink-mute">
            <span className="text-accent text-[13px]">↓</span> parallel
          </span>
        </div>
        </div>

        {/* Canvas viewport — desktop pan/zoom surface. */}
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
    </div>
  );
}
