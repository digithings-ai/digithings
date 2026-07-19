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

import PipelineCanvas, { focusRectForTarget, movePipelineStage } from './PipelineCanvas';
import type { PipelineDayData } from '@/lib/pipeline-graph-data';
import type { PipelineStageId } from '@/lib/pipeline-topology';
import type { LaidOutNode } from '@/lib/pipeline-layout';

const emptyDay: PipelineDayData = {
  fanoutCounts: {},
  fanoutKeys: {},
  presentKeys: new Set(),
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

  it('contains toolbar buttons: Fit, Expand all, Collapse', () => {
    const html = renderToStaticMarkup(
      createElement(PipelineCanvas, { day: emptyDay, onNodeActivate: () => {} }),
    );
    expect(html).toContain('Fit');
    expect(html).toContain('Expand all');
    expect(html).toContain('Collapse');
  });

  it('keeps previous and next stage walkthrough controls in the canvas toolbar', () => {
    const html = renderToStaticMarkup(
      createElement(PipelineCanvas, { day: emptyDay, onNodeActivate: () => {} }),
    );

    expect(html).toContain('Previous pipeline stage');
    expect(html).toContain('Next pipeline stage');
    expect(html).toContain(`1 of 6`);
  });

  it('clips the camera viewport without creating a competing native scroll container', () => {
    const html = renderToStaticMarkup(
      createElement(PipelineCanvas, { day: emptyDay, onNodeActivate: () => {} }),
    );

    expect(html).toContain('overflow-clip');
    expect(html).not.toContain('select-none overflow-hidden cursor-grab');
  });

  it('renders a touch-first section navigator with the first stage expanded', () => {
    const html = renderToStaticMarkup(
      createElement(PipelineCanvas, { day: emptyDay, onNodeActivate: () => {} }),
    );

    expect(html).toContain('Previous pipeline section');
    expect(html).toContain('Next pipeline section');
    expect(html).toContain('Stage 1 of 6');
    expect(html).toContain('Preflight / market data');
    expect(html).toContain('md:hidden');
  });

  it('clamps mobile section navigation at both ends', () => {
    expect(movePipelineStage(0, -1)).toBe(0);
    expect(movePipelineStage(0, 1)).toBe(1);
    expect(movePipelineStage(5, 1)).toBe(5);
  });
});

describe('focusRectForTarget', () => {
  const nodes: LaidOutNode[] = [
    { id: 'research', kind: 'stage', stageId: 'research', label: 'Research', x: 184, y: 0, width: 160, height: 48 },
    { id: 'research:sectors', kind: 'substep', stageId: 'research', label: 'Sectors', x: 368, y: 0, width: 160, height: 48 },
    { id: 'research:sectors:0', kind: 'fanout-branch', stageId: 'research', label: 'Technology', x: 368, y: 60, width: 160, height: 48 },
    { id: 'research:sectors:1', kind: 'fanout-branch', stageId: 'research', label: 'Financials', x: 368, y: 120, width: 160, height: 48 },
    { id: 'synthesis', kind: 'stage', stageId: 'synthesis', label: 'Synthesis', x: 552, y: 0, width: 160, height: 48 },
  ];

  it('returns the full revealed stage bounds', () => {
    expect(focusRectForTarget(nodes, { kind: 'stage', stageId: 'research' })).toEqual({
      x: 184,
      y: 0,
      width: 344,
      height: 168,
    });
  });

  it('limits fan-out focus to its parent and branches', () => {
    expect(focusRectForTarget(nodes, { kind: 'fanout', nodeId: 'research:sectors' })).toEqual({
      x: 368,
      y: 0,
      width: 160,
      height: 168,
    });
  });
});
