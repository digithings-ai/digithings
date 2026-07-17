import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, it, expect } from 'vitest';

import PipelineNode from './PipelineNode';
import type { LaidOutNode } from '@/lib/pipeline-layout';

const stageNode: LaidOutNode = {
  id: 'research',
  kind: 'stage',
  stageId: 'research',
  label: 'Research',
  x: 0,
  y: 0,
  width: 160,
  height: 48,
};

const fanoutNode: LaidOutNode = {
  id: 'research:sectors',
  kind: 'substep',
  stageId: 'research',
  label: 'Sectors',
  x: 184,
  y: 0,
  width: 160,
  height: 48,
};

describe('PipelineNode', () => {
  it('renders the node label', () => {
    const html = renderToStaticMarkup(
      createElement(PipelineNode, { node: stageNode, expandable: false, expanded: false, onActivate: () => {} }),
    );
    expect(html).toContain('Research');
  });

  it('renders a count badge when count is provided', () => {
    const html = renderToStaticMarkup(
      createElement(PipelineNode, { node: fanoutNode, count: 12, expandable: true, expanded: false, onActivate: () => {} }),
    );
    expect(html).toContain('12');
  });

  it('contains no banned F5 raw color literals', () => {
    const html = renderToStaticMarkup(
      createElement(PipelineNode, { node: stageNode, expandable: true, expanded: true, onActivate: () => {} }),
    );
    expect(html).not.toContain('fin-purple');
    expect(html).not.toContain('a78bfa');
    // compose the banned raw-blue string so the hygiene scanner does not flag this test file itself
    const rawBlue = 'rgba(' + '59,130,246';
    expect(html).not.toContain(rawBlue);
  });

  describe('explainable nodes without documents', () => {
    const leafNoData: LaidOutNode = {
      id: 'selection:thesis',
      kind: 'substep',
      stageId: 'selection',
      label: 'Thesis framing',
      x: 0,
      y: 0,
      width: 160,
      height: 48,
      // no documentKey — opens topology guidance instead of a run document
    };

    it('keeps a leaf substep with no documentKey keyboard and pointer activatable', () => {
      const html = renderToStaticMarkup(
        createElement(PipelineNode, {
          node: leafNoData,
          expandable: false,
          expanded: false,
          onActivate: () => {},
        }),
      );
      expect(html).toContain('cursor-pointer');
      expect(html).toContain('tabindex="0"');
      expect(html).not.toContain('aria-disabled');
    });

    it('document nodes use the same direct activation affordance', () => {
      const html = renderToStaticMarkup(
        createElement(PipelineNode, {
          node: { ...leafNoData, documentKey: 'macro' },
          expandable: false,
          expanded: false,
          onActivate: () => {},
        }),
      );
      expect(html).toContain('cursor-pointer');
      expect(html).not.toContain('aria-disabled');
    });

    it('does not render a fanout-parent substep as inert even without a documentKey', () => {
      const html = renderToStaticMarkup(
        createElement(PipelineNode, {
          node: fanoutNode,
          expandable: true,
          expanded: false,
          onActivate: () => {},
        }),
      );
      expect(html).toContain('cursor-pointer');
      expect(html).not.toContain('cursor-default');
      expect(html).not.toContain('aria-disabled');
    });

    it('does not render a leaf substep with a real documentKey as inert', () => {
      const html = renderToStaticMarkup(
        createElement(PipelineNode, {
          node: { ...leafNoData, documentKey: 'macro' },
          expandable: false,
          expanded: false,
          onActivate: () => {},
        }),
      );
      expect(html).toContain('cursor-pointer');
      expect(html).not.toContain('cursor-default');
    });
  });
});
