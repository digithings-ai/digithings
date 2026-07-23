'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  BookOpen,
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

export function buildPipelineWalkthrough(day: PipelineDayData): LaidOutNode[] {
  const expandedStages = new Set<PipelineStageId>();
  const expandedFanouts = new Set<string>();
  for (const stage of PIPELINE_TOPOLOGY) {
    expandedStages.add(stage.id);
    for (const subStep of stage.subSteps) {
      if (subStep.fanout) expandedFanouts.add(`${stage.id}:${subStep.id}`);
    }
  }

  return layoutPipeline(day, { expandedStages, expandedFanouts }).nodes.filter(
    (node) => node.kind !== 'fanout-branch' || node.documentKey,
  );
}

export function movePipelineWalkthrough(
  index: number,
  direction: -1 | 1,
  itemCount: number,
): number {
  return Math.max(0, Math.min(itemCount - 1, index + direction));
}

export function findPipelineWalkthroughIndex(
  nodes: LaidOutNode[],
  selectedNodeId?: string,
): number {
  if (!selectedNodeId) return -1;
  return nodes.findIndex(
    (node) => node.id === selectedNodeId || node.documentKey === selectedNodeId,
  );
}

export function mobileWalkthroughScrollTarget(
  nodes: LaidOutNode[],
  activeNode?: LaidOutNode,
): 'start' | LaidOutNode | null {
  if (!activeNode) return null;
  if (activeNode.kind === 'stage') return 'start';
  return nodes.find((node) => node.id === activeNode.id) ?? null;
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
  const [activeWalkthroughIndex, setActiveWalkthroughIndex] = useState(0);
  const [isWalkthroughNavigating, setIsWalkthroughNavigating] = useState(false);
  const [focusTarget, setFocusTarget] = useState<PipelineFocusTarget | null>(() =>
    selectedNodeId ? { kind: 'document', documentKey: selectedNodeId } : null,
  );
  const mobileListRef = useRef<HTMLDivElement | null>(null);
  const camera = useCanvasCamera();
  const { viewportRef, layerRef, fit, focusOn } = camera;

  const layout = useMemo(() => layoutPipeline(day, expansion), [day, expansion]);
  const walkthroughNodes = useMemo(() => buildPipelineWalkthrough(day), [day]);
  const selectedWalkthroughIndex = findPipelineWalkthroughIndex(walkthroughNodes, selectedNodeId);
  const resolvedWalkthroughIndex = !isWalkthroughNavigating && selectedWalkthroughIndex >= 0
    ? selectedWalkthroughIndex
    : Math.min(activeWalkthroughIndex, Math.max(0, walkthroughNodes.length - 1));
  const activeWalkthroughNode = walkthroughNodes[resolvedWalkthroughIndex] ?? walkthroughNodes[0];
  const selectedStageIndex = !isWalkthroughNavigating && selectedWalkthroughIndex >= 0
    ? PIPELINE_TOPOLOGY.findIndex(
        (stage) => stage.id === walkthroughNodes[selectedWalkthroughIndex]?.stageId,
      )
    : -1;
  const resolvedStageIndex = selectedStageIndex >= 0 ? selectedStageIndex : activeStageIndex;
  const activeStage = PIPELINE_TOPOLOGY[resolvedStageIndex];
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
    const list = mobileListRef.current;
    const target = mobileWalkthroughScrollTarget(mobileNodes, activeWalkthroughNode);
    if (!target || !list) return;

    const frame = requestAnimationFrame(() => {
      if (target === 'start') {
        list.scrollTo({ top: 0, behavior: 'smooth' });
        return;
      }
      list
        .querySelector<HTMLElement>(`[data-mobile-node-id="${CSS.escape(target.id)}"]`)
        ?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
    return () => cancelAnimationFrame(frame);
  }, [activeWalkthroughNode, mobileNodes]);

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
      setIsWalkthroughNavigating(false);
      const stageIndex = PIPELINE_TOPOLOGY.findIndex((stage) => stage.id === node.stageId);
      if (stageIndex >= 0) setActiveStageIndex(stageIndex);
      const walkthroughIndex = walkthroughNodes.findIndex((candidate) => candidate.id === node.id);
      if (walkthroughIndex >= 0) setActiveWalkthroughIndex(walkthroughIndex);

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
    [expansion.expandedFanouts, expansion.expandedStages, onNodeActivate, walkthroughNodes],
  );

  const selectWalkthroughNode = useCallback((
    node: LaidOutNode,
    index: number,
    openDetail = true,
  ) => {
    const stageIndex = PIPELINE_TOPOLOGY.findIndex((stage) => stage.id === node.stageId);
    const subStepId = node.id.split(':')[1];
    const fanoutKey = subStepId ? `${node.stageId}:${subStepId}` : null;
    const subStep = subStepId
      ? stageById(node.stageId)?.subSteps.find((candidate) => candidate.id === subStepId)
      : undefined;

    setActiveWalkthroughIndex(index);
    setIsWalkthroughNavigating(!openDetail);
    if (stageIndex >= 0) setActiveStageIndex(stageIndex);
    setExpansion({
      expandedStages: new Set([node.stageId]),
      expandedFanouts: new Set(fanoutKey && (subStep?.fanout || node.kind === 'fanout-branch')
        ? [fanoutKey]
        : []),
    });
    setFocusTarget(
      node.kind === 'stage'
        ? { kind: 'stage', stageId: node.stageId }
        : subStep?.fanout && node.kind === 'substep'
          ? { kind: 'fanout', nodeId: node.id }
          : { kind: 'node', nodeId: node.id },
    );
    if (openDetail) onNodeActivate(node);
  }, [onNodeActivate]);

  const walkPipeline = useCallback((direction: -1 | 1) => {
    const nextIndex = movePipelineWalkthrough(
      resolvedWalkthroughIndex,
      direction,
      walkthroughNodes.length,
    );
    const node = walkthroughNodes[nextIndex];
    if (node) selectWalkthroughNode(node, nextIndex, false);
  }, [resolvedWalkthroughIndex, selectWalkthroughNode, walkthroughNodes]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      const target = event.target instanceof HTMLElement ? event.target : null;
      if (
        target?.isContentEditable
        || target?.closest('input, textarea, select, [role="textbox"], a')
      ) return;

      // Keep native Space activation on focused controls; arrow traversal remains
      // available after clicking the toolbar.
      if (event.code === 'Space' && target?.closest('button')) return;

      let direction: -1 | 1 | null = null;
      if (event.key === 'ArrowLeft') direction = -1;
      if (event.key === 'ArrowRight') direction = 1;
      if (event.code === 'Space') direction = event.shiftKey ? -1 : 1;
      if (direction === null) return;

      event.preventDefault();
      walkPipeline(direction);
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [walkPipeline]);

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
        <div
          ref={mobileListRef}
          className="min-h-0 flex-1 overflow-y-auto px-4 py-4 pb-[calc(7rem+env(safe-area-inset-bottom))]"
        >
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
              const selected = node.id === activeWalkthroughNode?.id;

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
                  </span>
                  {count != null && count > 0 ? (
                    <span className="rounded-full bg-accent/15 px-2 py-0.5 font-mono text-xs tabular-nums text-accent">
                      {count}
                    </span>
                  ) : null}
                  {expandable ? (
                    expanded ? <ChevronDown size={16} aria-hidden /> : <ChevronRight size={16} aria-hidden />
                  ) : null}
                </button>
              );
            })}
          </div>
        </div>

        <div className="fixed inset-x-0 bottom-0 z-30 border-y border-hair bg-surface/95 px-4 pt-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] backdrop-blur-md">
          <div className="flex items-center gap-3">
            <button
              type="button"
              aria-label="Previous pipeline section"
              disabled={resolvedWalkthroughIndex === 0}
              onClick={() => walkPipeline(-1)}
              className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-hair text-ink transition-colors hover:border-accent/50 hover:text-accent disabled:cursor-not-allowed disabled:opacity-30"
            >
              <ChevronLeft size={20} aria-hidden />
            </button>
            <div className="min-w-0 flex-1 text-center">
              <span className="block font-mono text-xs uppercase text-ink-mute">
                {resolvedWalkthroughIndex + 1} of {walkthroughNodes.length}
              </span>
              <span className="mt-0.5 block truncate font-display text-xl text-ink">
                {activeWalkthroughNode?.label ?? activeStage.label}
              </span>
            </div>
            <button
              type="button"
              aria-label="Next pipeline section"
              disabled={resolvedWalkthroughIndex === walkthroughNodes.length - 1}
              onClick={() => walkPipeline(1)}
              className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-hair text-ink transition-colors hover:border-accent/50 hover:text-accent disabled:cursor-not-allowed disabled:opacity-30"
            >
              <ChevronRight size={20} aria-hidden />
            </button>
          </div>
          <div className="mt-3 grid grid-cols-6 gap-1" aria-hidden>
            {PIPELINE_TOPOLOGY.map((stage, index) => (
              <span
                key={stage.id}
                className={`h-1 rounded-full ${index === resolvedStageIndex ? 'bg-accent' : 'bg-hair'}`}
              />
            ))}
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
              <div
                role="toolbar"
                aria-label="Pipeline controls"
                data-no-pan=""
                className="pointer-events-auto inline-flex items-center gap-1 rounded-lg border border-hair bg-term-bg/95 p-1 shadow-sm backdrop-blur-md"
              >
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
                <Tooltip>
                  <TooltipTrigger
                    render={(
                      <IconButton aria-label="Expand all" data-no-pan="" onClick={handleExpandAll}>
                        <ChevronsDown size={15} aria-hidden />
                      </IconButton>
                    )}
                  />
                  <TooltipContent skin="reference" side="bottom">Expand all</TooltipContent>
                </Tooltip>
                <Tooltip>
                  <TooltipTrigger
                    render={(
                      <IconButton aria-label="Collapse all" data-no-pan="" onClick={handleCollapseAll}>
                        <ChevronsUp size={15} aria-hidden />
                      </IconButton>
                    )}
                  />
                  <TooltipContent skin="reference" side="bottom">Collapse all</TooltipContent>
                </Tooltip>
                <span className="mx-1 h-5 w-px bg-hair" aria-hidden />
                <Tooltip>
                  <TooltipTrigger
                    render={(
                      <IconButton
                        aria-label="Previous pipeline section"
                        aria-keyshortcuts="ArrowLeft Shift+Space"
                        data-no-pan=""
                        disabled={resolvedWalkthroughIndex === 0}
                        onClick={() => walkPipeline(-1)}
                      >
                        <ChevronLeft size={15} aria-hidden />
                      </IconButton>
                    )}
                  />
                  <TooltipContent skin="reference" side="bottom">Previous section</TooltipContent>
                </Tooltip>
                <Tooltip>
                  <TooltipTrigger
                    render={(
                      <IconButton
                        aria-label={`Open ${activeWalkthroughNode?.label ?? activeStage.label} pipeline section (${resolvedWalkthroughIndex + 1} of ${walkthroughNodes.length})`}
                        data-no-pan=""
                        onClick={() => activeWalkthroughNode
                          && selectWalkthroughNode(activeWalkthroughNode, resolvedWalkthroughIndex)}
                      >
                        <BookOpen size={15} aria-hidden />
                      </IconButton>
                    )}
                  />
                  <TooltipContent skin="reference" side="bottom">
                    {resolvedWalkthroughIndex + 1} of {walkthroughNodes.length}
                    {' · '}
                    {activeWalkthroughNode?.label ?? activeStage.label}
                  </TooltipContent>
                </Tooltip>
                <Tooltip>
                  <TooltipTrigger
                    render={(
                      <IconButton
                        aria-label="Next pipeline section"
                        aria-keyshortcuts="ArrowRight Space"
                        data-no-pan=""
                        disabled={resolvedWalkthroughIndex === walkthroughNodes.length - 1}
                        onClick={() => walkPipeline(1)}
                      >
                        <ChevronRight size={15} aria-hidden />
                      </IconButton>
                    )}
                  />
                  <TooltipContent skin="reference" side="bottom">Next section</TooltipContent>
                </Tooltip>
              </div>
            </TooltipProvider>

            <div className="hidden items-center gap-3 rounded-lg border border-hair bg-term-bg/90 px-3 py-2 font-mono text-xs text-ink-mute backdrop-blur-md xl:flex">
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
