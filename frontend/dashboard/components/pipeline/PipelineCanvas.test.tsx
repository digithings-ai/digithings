import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, it, expect, vi } from 'vitest';

vi.mock('@/components/pipeline/useCanvasCamera', async (importOriginal) => {
  const orig = await importOriginal<typeof import('./useCanvasCamera')>();
  return {
    ...orig,
    useCanvasCamera: () => ({
      transform: { x: 0, y: 0, scale: 1 },
      zoomIn: () => {},
      zoomOut: () => {},
      fit: () => {},
      centerOn: () => {},
      focusOn: () => {},
      layerRef: { current: null },
      viewportRef: { current: null },
      bind: {
        onPointerDown: () => {},
        onPointerMove: () => {},
        onPointerUp: () => {},
        onPointerCancel: () => {},
      },
    }),
  };
});

import PipelineCanvas, {
  buildPipelineWalkthrough,
  findPipelineWalkthroughIndex,
  focusRectForTarget,
  mobileWalkthroughScrollTarget,
  movePipelineWalkthrough,
  planCanvasNodeClick,
  planWalkthroughSelection,
  walkthroughModeFromViewport,
  walkthroughNavigationTarget,
} from './PipelineCanvas';
import type { PipelineDayData } from '@/lib/pipeline-graph-data';
import type { PipelineStageId } from '@/lib/pipeline-topology';
import type { LaidOutNode } from '@/lib/pipeline-layout';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const emptyDay: PipelineDayData = {
  fanoutCounts: {},
  fanoutKeys: {},
  presentKeys: new Set(),
  artifacts: [],
};

describe('PipelineCanvas', () => {
  it('renders all 6 stage labels in collapsed state', () => {
    const html = renderToStaticMarkup(
      createElement(PipelineCanvas, { day: emptyDay, onNodeActivate: () => {} }),
    );
    for (const label of ['Inputs', 'Research', 'Synthesis', 'Selection', 'Decision', 'Learning']) {
      expect(html).toContain(label);
    }
  });

  it('renders research sub-step labels when research is initially expanded', () => {
    const html = renderToStaticMarkup(
      createElement(PipelineCanvas, {
        day: emptyDay,
        initialExpansion: { expandedStages: new Set<PipelineStageId>(['research']), expandedFanouts: new Set<string>() },
        onNodeActivate: () => {},
      }),
    );
    expect(html).toContain('Alt-data');
    expect(html).toContain('Sectors');
  });

  it('renders every canvas control as an accessible icon in one toolbar', () => {
    const html = renderToStaticMarkup(
      createElement(PipelineCanvas, { day: emptyDay, onNodeActivate: () => {} }),
    );

    expect(html).toContain('aria-label="Pipeline controls"');
    expect(html).toContain('aria-label="Fit pipeline to view"');
    expect(html).toContain('aria-label="Expand all"');
    expect(html).toContain('aria-label="Collapse all"');
    expect(html).not.toContain('aria-label="Pipeline view controls"');
    expect(html).not.toContain('aria-label="Pipeline walkthrough"');
  });

  it('walks every stage and subsection from the canvas toolbar', () => {
    const html = renderToStaticMarkup(
      createElement(PipelineCanvas, { day: emptyDay, onNodeActivate: () => {} }),
    );

    expect(html).toContain('Previous pipeline section');
    expect(html).toContain('Next pipeline section');
    // Decision/commit is graph-hidden; walkthrough is stages + visible sub-steps.
    expect(html).toContain('1 of 23');
    expect(buildPipelineWalkthrough(emptyDay).map((node) => node.label)).toContain('Risk sizing');
    expect(buildPipelineWalkthrough(emptyDay).some((node) => node.id === 'decision:commit')).toBe(false);
  });

  it('adds real fan-out artifacts to the walkthrough without placeholder stops', () => {
    const day: PipelineDayData = {
      fanoutCounts: { 'alt-data': 1 },
      fanoutKeys: { 'alt-data': ['alt-onchain-positioning'] },
      presentKeys: new Set(['alt-onchain-positioning']),
      artifacts: [],
    };
    const nodes = buildPipelineWalkthrough(day);

    expect(nodes).toHaveLength(24);
    expect(nodes.find((node) => node.documentKey === 'alt-onchain-positioning')).toBeDefined();
    expect(nodes.some((node) => node.label === 'Alt-data 2')).toBe(false);
  });

  it('clips the camera viewport without creating a competing native scroll container', () => {
    const html = renderToStaticMarkup(
      createElement(PipelineCanvas, { day: emptyDay, onNodeActivate: () => {} }),
    );

    expect(html).toContain('overflow-clip');
    expect(html).not.toContain('select-none overflow-hidden cursor-grab');
  });

  it('renders a touch-first navigator over the complete walkthrough', () => {
    const html = renderToStaticMarkup(
      createElement(PipelineCanvas, { day: emptyDay, onNodeActivate: () => {} }),
    );

    expect(html).toContain('Previous pipeline section');
    expect(html).toContain('Next pipeline section');
    expect(html).toContain('1 of 23');
    expect(html).toContain('Preflight / market data');
    expect(html).toContain('md:hidden');
    expect(html).toContain('fixed inset-x-0 bottom-0');
    expect(html).toContain('pb-[calc(7rem+env(safe-area-inset-bottom))]');
    expect(html).not.toContain('Run artifact');
    expect(html).not.toContain('About this step');
    expect(html).not.toContain('>Open<');
    expect(html).not.toContain('>About<');
    expect(html).not.toContain('Pipeline guide');
  });

  it('clamps full walkthrough keyboard navigation at both ends', () => {
    expect(movePipelineWalkthrough(0, -1, 23)).toBe(0);
    expect(movePipelineWalkthrough(0, 1, 23)).toBe(1);
    expect(movePipelineWalkthrough(22, 1, 23)).toBe(22);
  });

  it('opens the selected walkthrough stop during desktop arrow traversal', () => {
    const nodes = buildPipelineWalkthrough(emptyDay);

    expect(walkthroughNavigationTarget(nodes, 0, 1, 'desktop')).toEqual({
      index: 1,
      node: nodes[1],
      openDetail: true,
    });
  });

  it('only highlights the selected walkthrough stop during mobile arrow traversal', () => {
    const nodes = buildPipelineWalkthrough(emptyDay);

    expect(walkthroughNavigationTarget(nodes, 0, 1, 'mobile')).toEqual({
      index: 1,
      node: nodes[1],
      openDetail: false,
    });
  });

  it('maps md+ viewports to desktop open and narrower viewports to mobile no-open', () => {
    expect(walkthroughModeFromViewport(true)).toBe('desktop');
    expect(walkthroughModeFromViewport(false)).toBe('mobile');
  });

  it('desktop walkthrough expands the stop but opens detail only when a document exists', () => {
    const nodes = buildPipelineWalkthrough(emptyDay);
    const target = walkthroughNavigationTarget(nodes, 0, 1, 'desktop');
    expect(target).not.toBeNull();
    const plan = planWalkthroughSelection(target!.node, target!.openDetail);

    expect(target!.openDetail).toBe(true);
    expect(plan.activateDetail).toBe(Boolean(target!.node.documentKey));
    expect([...plan.expansion.expandedStages]).toEqual([target!.node.stageId]);
    expect(plan.focusTarget).toEqual(
      target!.node.kind === 'stage'
        ? { kind: 'stage', stageId: target!.node.stageId }
        : { kind: 'node', nodeId: target!.node.id },
    );
  });

  it('mobile walkthrough steps expand the stop without opening detail', () => {
    const nodes = buildPipelineWalkthrough(emptyDay);
    const leaf = nodes.find((node) => node.kind === 'substep' && !node.id.includes('alt-data'));
    expect(leaf).toBeDefined();
    const index = nodes.indexOf(leaf!);
    const target = walkthroughNavigationTarget(nodes, Math.max(0, index - 1), 1, 'mobile');
    expect(target).not.toBeNull();
    const plan = planWalkthroughSelection(target!.node, target!.openDetail);

    expect(plan.activateDetail).toBe(false);
    expect(plan.expansion.expandedStages.has(target!.node.stageId)).toBe(true);
  });

  it('expands fan-out parents on both desktop and mobile without changing open/no-open', () => {
    const day: PipelineDayData = {
      fanoutCounts: { 'alt-data': 1 },
      fanoutKeys: { 'alt-data': ['alt-onchain-positioning'] },
      presentKeys: new Set(['alt-onchain-positioning']),
      artifacts: [],
    };
    const nodes = buildPipelineWalkthrough(day);
    const fanoutParent = nodes.find((node) => node.id === 'research:alt-data');
    expect(fanoutParent).toBeDefined();

    const desktop = planWalkthroughSelection(fanoutParent!, true);
    const mobile = planWalkthroughSelection(fanoutParent!, false);

    expect(desktop.activateDetail).toBe(false);
    expect(mobile.activateDetail).toBe(false);
    expect([...desktop.expansion.expandedFanouts]).toEqual(['research:alt-data']);
    expect([...mobile.expansion.expandedFanouts]).toEqual(['research:alt-data']);
    expect(desktop.focusTarget).toEqual({ kind: 'fanout', nodeId: 'research:alt-data' });
    expect(mobile.focusTarget).toEqual({ kind: 'fanout', nodeId: 'research:alt-data' });
  });

  it('wires desktop toolbar to open-mode walkthrough and mobile dock to no-open', () => {
    const source = readFileSync(
      join(dirname(fileURLToPath(import.meta.url)), 'PipelineCanvas.tsx'),
      'utf8',
    );

    expect(source).toContain("onClick={() => walkPipeline(-1, 'desktop')}");
    expect(source).toContain("onClick={() => walkPipeline(1, 'desktop')}");
    expect(source).toContain("onClick={() => walkPipeline(-1, 'mobile')}");
    expect(source).toContain("onClick={() => walkPipeline(1, 'mobile')}");
    // Explicit Open control still activates detail on the current stop.
    expect(source).toContain(
      '&& selectWalkthroughNode(activeWalkthroughNode, resolvedWalkthroughIndex)}',
    );
  });

  it('synchronizes a selected node or artifact with the walkthrough', () => {
    const day: PipelineDayData = {
      fanoutCounts: { 'alt-data': 1 },
      fanoutKeys: { 'alt-data': ['alt-onchain-positioning'] },
      presentKeys: new Set(['alt-onchain-positioning']),
      artifacts: [],
    };
    const nodes = buildPipelineWalkthrough(day);

    expect(findPipelineWalkthroughIndex(nodes, 'research:sectors')).toBeGreaterThan(0);
    expect(findPipelineWalkthroughIndex(nodes, 'alt-onchain-positioning')).toBeGreaterThan(0);
    expect(findPipelineWalkthroughIndex(nodes, 'missing')).toBe(-1);
  });

  it('scrolls stage stops to the section start and node stops to their row', () => {
    const stage = {
      id: 'research',
      kind: 'stage',
      stageId: 'research',
      label: 'Research',
      x: 0,
      y: 0,
      width: 160,
      height: 48,
    } satisfies LaidOutNode;
    const node = {
      id: 'research:sectors',
      kind: 'substep',
      stageId: 'research',
      label: 'Sectors',
      x: 0,
      y: 0,
      width: 160,
      height: 48,
    } satisfies LaidOutNode;

    expect(mobileWalkthroughScrollTarget([node], stage)).toBe('start');
    expect(mobileWalkthroughScrollTarget([node], node)).toBe(node);
  });
});

describe('planCanvasNodeClick', () => {
  const emptyExpansion = { expandedStages: new Set<PipelineStageId>(), expandedFanouts: new Set<string>() };

  it('stage clicks expand in place and do not activate without a document', () => {
    const research: LaidOutNode = {
      id: 'research',
      kind: 'stage',
      stageId: 'research',
      label: 'Research',
      x: 184,
      y: 0,
      width: 160,
      height: 48,
    };
    const plan = planCanvasNodeClick(research, emptyExpansion);
    expect(plan.activate).toBe(false);
    expect([...plan.expansion.expandedStages]).toEqual(['research']);
    expect(plan.focusTarget).toEqual({ kind: 'stage', stageId: 'research' });
  });

  it('Decision with pm-rebalance activates the booked book without a guide pane', () => {
    const decision: LaidOutNode = {
      id: 'decision',
      kind: 'stage',
      stageId: 'decision',
      label: 'Decision',
      x: 736,
      y: 0,
      width: 160,
      height: 48,
      documentKey: 'pm-rebalance',
    };
    const plan = planCanvasNodeClick(decision, emptyExpansion);
    expect(plan.activate).toBe(true);
    expect([...plan.expansion.expandedStages]).toEqual([]);
    expect(plan.focusTarget).toEqual({ kind: 'node', nodeId: 'decision' });
  });

  it('fan-out parents expand under the row and do not open the sidebar', () => {
    const alt: LaidOutNode = {
      id: 'research:alt-data',
      kind: 'substep',
      stageId: 'research',
      label: 'Alt-data',
      x: 184,
      y: 60,
      width: 160,
      height: 48,
    };
    const plan = planCanvasNodeClick(alt, {
      expandedStages: new Set(['research']),
      expandedFanouts: new Set(),
    });
    expect(plan.activate).toBe(false);
    expect([...plan.expansion.expandedFanouts]).toEqual(['research:alt-data']);
  });

  it('named documents open the sidebar', () => {
    const digest: LaidOutNode = {
      id: 'synthesis:digest',
      kind: 'substep',
      stageId: 'synthesis',
      label: 'Daily digest',
      x: 368,
      y: 60,
      width: 160,
      height: 48,
      documentKey: 'digest-delta',
    };
    const plan = planCanvasNodeClick(digest, {
      expandedStages: new Set(['synthesis']),
      expandedFanouts: new Set(),
    });
    expect(plan.activate).toBe(true);
    expect(plan.focusTarget).toEqual({ kind: 'node', nodeId: 'synthesis:digest' });
  });

  it('state-only leaves do not open the sidebar', () => {
    const thesis: LaidOutNode = {
      id: 'selection:thesis',
      kind: 'substep',
      stageId: 'selection',
      label: 'Thesis framing',
      x: 552,
      y: 60,
      width: 160,
      height: 48,
      stateOnly: true,
    };
    const plan = planCanvasNodeClick(thesis, {
      expandedStages: new Set(['selection']),
      expandedFanouts: new Set(),
    });
    expect(plan.activate).toBe(false);
  });
});

describe('focusRectForTarget', () => {
  const nodes: LaidOutNode[] = [
    { id: 'research', kind: 'stage', stageId: 'research', label: 'Research', x: 184, y: 0, width: 160, height: 48 },
    { id: 'research:sectors', kind: 'substep', stageId: 'research', label: 'Sectors', x: 184, y: 60, width: 160, height: 48 },
    { id: 'research:sectors:0', kind: 'fanout-branch', stageId: 'research', label: 'Technology', x: 184, y: 120, width: 160, height: 48 },
    { id: 'research:sectors:1', kind: 'fanout-branch', stageId: 'research', label: 'Financials', x: 184, y: 180, width: 160, height: 48 },
    { id: 'synthesis', kind: 'stage', stageId: 'synthesis', label: 'Synthesis', x: 368, y: 0, width: 160, height: 48 },
  ];

  it('returns the full revealed stage bounds stacked under the card', () => {
    expect(focusRectForTarget(nodes, { kind: 'stage', stageId: 'research' })).toEqual({
      x: 184,
      y: 0,
      width: 160,
      height: 228,
    });
  });

  it('limits fan-out focus to its parent and branches', () => {
    expect(focusRectForTarget(nodes, { kind: 'fanout', nodeId: 'research:sectors' })).toEqual({
      x: 184,
      y: 60,
      width: 160,
      height: 168,
    });
  });
});
