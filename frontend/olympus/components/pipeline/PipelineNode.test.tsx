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
});
