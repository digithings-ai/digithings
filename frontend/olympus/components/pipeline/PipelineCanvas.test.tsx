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

import PipelineCanvas, { movePipelineStage } from './PipelineCanvas';
import type { PipelineDayData } from '@/lib/pipeline-graph-data';
import type { PipelineStageId } from '@/lib/pipeline-topology';

const emptyDay: PipelineDayData = {
  fanoutCounts: {},
  fanoutKeys: {},
  presentKeys: new Set(),
};

describe('PipelineCanvas', () => {
  it('renders all 5 stage labels in collapsed state', () => {
    const html = renderToStaticMarkup(
      createElement(PipelineCanvas, { day: emptyDay, onNodeActivate: () => {} }),
    );
    for (const label of ['Inputs', 'Research', 'Synthesis', 'Selection', 'Decision']) {
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

  it('page overflow is contained — vp wrapper has overflow-hidden', () => {
    const html = renderToStaticMarkup(
      createElement(PipelineCanvas, { day: emptyDay, onNodeActivate: () => {} }),
    );
    expect(html).toContain('overflow-hidden');
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
