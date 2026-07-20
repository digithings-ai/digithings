'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronsDown,
  ChevronsUp,
  Focus,
  Minus,
  Plus,
} from 'lucide-react';
import {
  IconButton,
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@digithings/web';
import type { PipelineDayData } from '@/lib/pipeline-graph-data';
import type { ExpansionState, LaidOutNode } from '@/lib/pipeline-layout';
import { layoutPipeline } from '@/lib/pipeline-layout';
import type { PipelineStageId } from '@/lib/pipeline-topology';
import { PIPELINE_TOPOLOGY, stageById } from '@/lib/pipeline-topology';
import type { NodeRect } from './useCanvasCamera';
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

export type PipelineFocusTarget =
  | { kind: 'node'; nodeId: string }
  | { kind: 'document'; documentKey: string }
  | { kind: 'stage'; stageId: PipelineStageId }
  | { kind: 'fanout'; nodeId: string };

function boundingRect(nodes: LaidOutNode[]): NodeRect | null {
  if (nodes.length === 0) return null;
  const left = Math.min(...nodes.map((node) => node.x));
  const top = Math.min(...nodes.map((node) => node.y));
  const right = Math.max(...nodes.map((node) => node.x + node.width));
  const bottom = Math.max(...nodes.map((node) => node.y + node.height));
  return { x: left, y: top, width: right - left, height: bottom - top };
}

function nodeRectForTarget(
  nodes: LaidOutNode[],
  target: PipelineFocusTarget,
): NodeRect | null {
  const node = target.kind === 'document'
    ? nodes.find((candidate) => candidate.documentKey === target.documentKey)
    : target.kind === 'stage'
      ? nodes.find((candidate) => candidate.kind === 'stage' && candidate.stageId === target.stageId)
      : nodes.find((candidate) => candidate.id === target.nodeId);
  return node ? { x: node.x, y: node.y, width: node.width, height: node.height } : null;
}

export function focusRectForTarget(
  nodes: LaidOutNode[],
  target: PipelineFocusTarget,
): NodeRect | null {
  if (target.kind === 'stage') {
    return boundingRect(nodes.filter((node) => node.stageId === target.stageId));
  }
  if (target.kind === 'fanout') {
    return boundingRect(
      nodes.filter(
        (node) => node.id === target.nodeId || node.id.startsWith(`${target.nodeId}:`),
      ),
    );
  }
  return nodeRectForTarget(nodes, target);
}

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
  const [activeStageIndex, setActiveStageIndex] = useState(() => {
    const initialStage = initialExpansion?.expandedStages.values().next().value;
    const index = PIPELINE_TOPOLOGY.findIndex((stage) => stage.id === initialStage);
    return index >= 0 ? index : 0;
  });
  const [focusTarget, setFocusTarget] = useState<PipelineFocusTarget | null>(() =>
    selectedNodeId ? { kind: 'document', documentKey: selectedNodeId } : null,
  );
  const mobileListRef = useRef<HTMLDivElement | null>(null);
  const camera = useCanvasCamera();
  const { viewportRef, layerRef, fit, focusOn } = camera;

  const layout = useMemo(() => layoutPipeline(day, expansion), [day, expansion]);
  const activeStage = PIPELINE_TOPOLOGY[activeStageIndex];
  const mobileNodes = useMemo(() => {
    const mobileExpansion: ExpansionState = {
      expandedStages: new Set([activeStage.id]),
      expandedFanouts: expansion.expandedFanouts,
    };
    return layoutPipeline(day, mobileExpansion).nodes.filter(
      (node) => node.stageId === activeStage.id && node.kind !== 'stage',
    );
  }, [activeStage.id, day, expansion.expandedFanouts]);

  useEffect(() => {
    if (!selectedNodeId) return;
    const selectedNode = mobileNodes.find(
      (node) => node.id === selectedNodeId || node.documentKey === selectedNodeId,
    );
    const list = mobileListRef.current;
    if (!selectedNode || !list) return;

    const frame = requestAnimationFrame(() => {
      list
        .querySelector<HTMLElement>(`[data-mobile-node-id="${CSS.escape(selectedNode.id)}"]`)
        ?.scrollIntoView({ block: 'nearest' });
    });
    return () => cancelAnimationFrame(frame);
  }, [mobileNodes, selectedNodeId]);

  const fitToViewport = useCallback(() => {
    const viewport = viewportRef.current;
    if (!viewport || viewport.clientWidth <= 0 || viewport.clientHeight <= 0) return;
    fit(
      { width: layout.width, height: layout.height },
      { width: viewport.clientWidth, height: viewport.clientHeight },
    );
  }, [fit, layout.height, layout.width, viewportRef]);

  const focusCameraTarget = useCallback((target: PipelineFocusTarget) => {
    const viewport = viewportRef.current;
    const rect = focusRectForTarget(layout.nodes, target);
    if (!viewport || !rect || viewport.clientWidth <= 0 || viewport.clientHeight <= 0) return;
    const focusesSingleNode = target.kind === 'node' || target.kind === 'document';
    focusOn(
      rect,
      { width: viewport.clientWidth, height: viewport.clientHeight },
      focusesSingleNode
        ? { padding: 72, maxScale: 1.2 }
        : {
            padding: 48,
            minScale: 0.68,
            maxScale: 1.05,
            anchor: nodeRectForTarget(layout.nodes, target) ?? undefined,
            safeArea: { top: 128, right: 48, bottom: 48, left: 48 },
          },
    );
  }, [focusOn, layout.nodes, viewportRef]);

  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;

    let frame: number | null = null;
    const scheduleFit = () => {
      if (frame !== null) cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        frame = null;
        if (focusTarget) focusCameraTarget(focusTarget);
        else fitToViewport();
      });
    };

    const observer = new ResizeObserver(scheduleFit);
    observer.observe(viewport);
    scheduleFit();

    return () => {
      observer.disconnect();
      if (frame !== null) cancelAnimationFrame(frame);
    };
  }, [fitToViewport, focusCameraTarget, focusTarget, viewportRef]);

  const handleNodeClick = useCallback(
    (node: LaidOutNode) => {
      const stageIndex = PIPELINE_TOPOLOGY.findIndex((stage) => stage.id === node.stageId);
      if (stageIndex >= 0) setActiveStageIndex(stageIndex);

      if (node.kind === 'stage') {
        const willExpand = !expansion.expandedStages.has(node.stageId);
        setFocusTarget(willExpand
          ? { kind: 'stage', stageId: node.stageId }
          : { kind: 'node', nodeId: node.id });
        setExpansion((prev) => {
          const next = new Set(prev.expandedStages);
          if (next.has(node.stageId)) {
            next.delete(node.stageId);
          } else {
            next.add(node.stageId);
          }
          return { ...prev, expandedStages: next };
        });
        onNodeActivate(node);
        return;
      }

      if (node.kind === 'substep') {
        const subStepId = node.id.split(':')[1];
        const hasFanout = !!stageById(node.stageId)?.subSteps.find((s) => s.id === subStepId)?.fanout;
        if (hasFanout) {
          const fanoutKey = `${node.stageId}:${subStepId}`;
          const willExpand = !expansion.expandedFanouts.has(fanoutKey);
          setFocusTarget(willExpand
            ? { kind: 'fanout', nodeId: node.id }
            : { kind: 'node', nodeId: node.id });
          setExpansion((prev) => {
            const next = new Set(prev.expandedFanouts);
            if (next.has(fanoutKey)) {
              next.delete(fanoutKey);
            } else {
              next.add(fanoutKey);
            }
            return { ...prev, expandedFanouts: next };
          });
          onNodeActivate(node);
          return;
        }
        setFocusTarget({ kind: 'node', nodeId: node.id });
        onNodeActivate(node);
        return;
      }

      // fanout-branch
      setFocusTarget({ kind: 'node', nodeId: node.id });
      onNodeActivate(node);
    },
    [expansion.expandedFanouts, expansion.expandedStages, onNodeActivate],
  );

  const selectWalkthroughStage = useCallback((stageIndex: number) => {
    const stage = PIPELINE_TOPOLOGY[stageIndex];
    if (!stage) return;

    const expandedFanouts = new Set(
      stage.subSteps
        .filter((subStep) => subStep.fanout)
        .map((subStep) => `${stage.id}:${subStep.id}`),
    );
    const stageNode = layout.nodes.find(
      (node) => node.kind === 'stage' && node.stageId === stage.id,
    );

    setActiveStageIndex(stageIndex);
    setExpansion({
      expandedStages: new Set([stage.id]),
      expandedFanouts,
    });
    setFocusTarget({ kind: 'stage', stageId: stage.id });
    if (stageNode) onNodeActivate(stageNode);
  }, [layout.nodes, onNodeActivate]);

  const walkStage = useCallback((direction: -1 | 1) => {
    selectWalkthroughStage(movePipelineStage(activeStageIndex, direction));
  }, [activeStageIndex, selectWalkthroughStage]);

  const handleFitClick = useCallback(() => {
    setFocusTarget(null);
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
    setFocusTarget(null);
    setExpansion({ expandedStages: allStages, expandedFanouts: allFanouts });
  }, []);

  const handleCollapseAll = useCallback(() => {
    setFocusTarget(null);
    setExpansion({ expandedStages: new Set(), expandedFanouts: new Set() });
  }, []);

  const { transform, zoomIn, zoomOut, bind } = camera;
  const handleZoomIn = useCallback(() => {
    setFocusTarget(null);
    zoomIn();
  }, [zoomIn]);
  const handleZoomOut = useCallback(() => {
    setFocusTarget(null);
    zoomOut();
  }, [zoomOut]);

  return (
    <div className="flex flex-col flex-1 min-h-0 min-w-0">
      <div className="flex min-h-0 flex-1 flex-col md:hidden">
        <div className="border-y border-hair bg-surface px-4 py-3">
          <div className="flex items-center gap-3">
            <button
              type="button"
              aria-label="Previous pipeline section"
              disabled={activeStageIndex === 0}
              onClick={() => walkStage(-1)}
              className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-hair text-ink transition-colors hover:border-accent/50 hover:text-accent disabled:cursor-not-allowed disabled:opacity-30"
            >
              <ChevronLeft size={20} aria-hidden />
            </button>
            <div className="min-w-0 flex-1 text-center">
              <span className="block font-mono text-[0.6rem] uppercase tracking-[0.1em] text-ink-mute">
                Stage {activeStageIndex + 1} of {PIPELINE_TOPOLOGY.length}
              </span>
              <span className="mt-0.5 block truncate font-display text-xl text-ink">
                {activeStage.label}
              </span>
            </div>
            <button
              type="button"
              aria-label="Next pipeline section"
              disabled={activeStageIndex === PIPELINE_TOPOLOGY.length - 1}
              onClick={() => walkStage(1)}
              className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-hair text-ink transition-colors hover:border-accent/50 hover:text-accent disabled:cursor-not-allowed disabled:opacity-30"
            >
              <ChevronRight size={20} aria-hidden />
            </button>
          </div>
          <div className="mt-3 grid grid-cols-6 gap-1" aria-hidden>
            {PIPELINE_TOPOLOGY.map((stage, index) => (
              <span
                key={stage.id}
                className={`h-1 rounded-full ${index === activeStageIndex ? 'bg-accent' : 'bg-hair'}`}
              />
            ))}
          </div>
        </div>

        <div ref={mobileListRef} className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
          <div className="border-l border-hair pl-3">
            {mobileNodes.map((node) => {
              const subStepId = node.kind === 'substep' ? node.id.split(':')[1] : undefined;
              const fanout = subStepId
                ? stageById(node.stageId)?.subSteps.find((step) => step.id === subStepId)?.fanout
                : undefined;
              const fanoutKey = subStepId ? `${node.stageId}:${subStepId}` : '';
              const expandable = Boolean(fanout);
              const expanded = expandable && expansion.expandedFanouts.has(fanoutKey);
              const count = fanout
                ? day.fanoutCounts[fanout.id] ?? fanout.defaultCount
                : undefined;
              const selected = Boolean(
                node.id === selectedNodeId
                  || (node.documentKey && node.documentKey === selectedNodeId),
              );

              return (
                <button
                  key={node.id}
                  type="button"
                  data-mobile-node-id={node.id}
                  aria-expanded={expandable ? expanded : undefined}
                  aria-current={selected ? 'step' : undefined}
                  onClick={() => handleNodeClick(node)}
                  className={`mb-2 flex min-h-14 w-full items-center gap-3 rounded-lg border px-3 py-2.5 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60 ${
                    node.kind === 'fanout-branch'
                      ? 'ml-4 w-[calc(100%-1rem)] border-hair bg-term-bg'
                      : 'border-hair bg-surface'
                  } hover:border-accent/50 hover:bg-accent/[0.04] ${
                    selected ? 'border-accent/60 shadow-[0_0_0_1px_var(--accent)]' : ''
                  }`}
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
                    <span className="mt-0.5 block text-[0.68rem] text-ink-mute">
                      {node.documentKey
                        ? 'Run artifact'
                        : expandable
                          ? 'Expand and learn'
                          : 'About this step'}
                    </span>
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
                  ) : (
                    <span className="font-mono text-[0.62rem] uppercase tracking-[0.08em] text-ink-mute">
                      About
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      <div className="hidden min-h-0 min-w-0 flex-1 flex-col md:flex">
        {/* Canvas viewport — desktop pan/zoom surface. */}
        <div
          ref={viewportRef}
          className="relative min-h-0 flex-1 select-none overflow-clip cursor-grab active:cursor-grabbing"
          style={{ touchAction: 'none', overscrollBehavior: 'contain' }}
          {...bind}
        >
          <div className="pointer-events-none absolute inset-x-0 top-0 z-20 flex items-start justify-between gap-3 p-4">
            <TooltipProvider delay={250}>
              <div className="pointer-events-auto flex flex-col items-start gap-2">
                <div
                  role="toolbar"
                  aria-label="Pipeline view controls"
                  data-no-pan=""
                  className="inline-flex items-center gap-1 rounded-lg border border-hair bg-term-bg/95 p-1 shadow-sm backdrop-blur-md"
                >
                <span className="px-2 font-mono text-[0.58rem] uppercase tracking-[0.1em] text-ink-mute">
                  View
                </span>
                <Tooltip>
                  <TooltipTrigger
                    render={(
                      <IconButton aria-label="Zoom out" data-no-pan="" onClick={handleZoomOut}>
                        <Minus size={15} aria-hidden />
                      </IconButton>
                    )}
                  />
                  <TooltipContent skin="reference" side="bottom">Zoom out</TooltipContent>
                </Tooltip>
                <Tooltip>
                  <TooltipTrigger
                    render={(
                      <IconButton
                        aria-label="Fit pipeline to view"
                        data-no-pan=""
                        onClick={handleFitClick}
                      >
                        <Focus size={15} aria-hidden />
                      </IconButton>
                    )}
                  />
                  <TooltipContent skin="reference" side="bottom">
                    Fit pipeline to view
                  </TooltipContent>
                </Tooltip>
                <Tooltip>
                  <TooltipTrigger
                    render={(
                      <IconButton aria-label="Zoom in" data-no-pan="" onClick={handleZoomIn}>
                        <Plus size={15} aria-hidden />
                      </IconButton>
                    )}
                  />
                  <TooltipContent skin="reference" side="bottom">Zoom in</TooltipContent>
                </Tooltip>
                <span className="mx-1 h-5 w-px bg-hair" aria-hidden />
                <button
                  type="button"
                  data-no-pan=""
                  onClick={handleExpandAll}
                  className="inline-flex h-8 items-center gap-1.5 rounded-md px-2.5 text-xs font-medium text-ink-mute transition-colors hover:bg-accent/10 hover:text-ink"
                >
                  <ChevronsDown size={14} aria-hidden />
                  Expand all
                </button>
                <button
                  type="button"
                  data-no-pan=""
                  onClick={handleCollapseAll}
                  className="inline-flex h-8 items-center gap-1.5 rounded-md px-2.5 text-xs font-medium text-ink-mute transition-colors hover:bg-accent/10 hover:text-ink"
                >
                  <ChevronsUp size={14} aria-hidden />
                  Collapse
                </button>
                </div>

                <div
                  role="group"
                  aria-label="Pipeline stage walkthrough"
                  data-no-pan=""
                  className="inline-flex h-9 items-center overflow-hidden rounded-lg border border-hair bg-term-bg/95 shadow-sm backdrop-blur-md"
                >
                  <button
                    type="button"
                    aria-label="Previous pipeline stage"
                    disabled={activeStageIndex === 0}
                    onClick={() => walkStage(-1)}
                    className="flex h-full w-9 items-center justify-center border-r border-hair text-ink-mute transition-colors hover:bg-accent/10 hover:text-ink disabled:cursor-not-allowed disabled:opacity-30"
                  >
                    <ChevronLeft size={15} aria-hidden />
                  </button>
                  <button
                    type="button"
                    aria-label={`Open ${activeStage.label} stage guide`}
                    onClick={() => selectWalkthroughStage(activeStageIndex)}
                    className="flex h-full min-w-36 items-center justify-between gap-3 px-3 text-left transition-colors hover:bg-accent/[0.06]"
                  >
                    <span className="font-mono text-[0.58rem] uppercase tracking-[0.08em] text-ink-mute">
                      {activeStageIndex + 1} of {PIPELINE_TOPOLOGY.length}
                    </span>
                    <span className="text-xs font-medium text-ink">{activeStage.label}</span>
                  </button>
                  <button
                    type="button"
                    aria-label="Next pipeline stage"
                    disabled={activeStageIndex === PIPELINE_TOPOLOGY.length - 1}
                    onClick={() => walkStage(1)}
                    className="flex h-full w-9 items-center justify-center border-l border-hair text-ink-mute transition-colors hover:bg-accent/10 hover:text-ink disabled:cursor-not-allowed disabled:opacity-30"
                  >
                    <ChevronRight size={15} aria-hidden />
                  </button>
                </div>
              </div>
            </TooltipProvider>

            <div className="hidden items-center gap-3 rounded-lg border border-hair bg-term-bg/90 px-3 py-2 font-mono text-[0.62rem] text-ink-mute backdrop-blur-md xl:flex">
              <span><span className="text-accent">→</span> sequential</span>
              <span><span className="text-accent">↓</span> parallel</span>
            </div>
          </div>

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
            const selected = node.id === selectedNodeId
              || (!!node.documentKey && node.documentKey === selectedNodeId);

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
