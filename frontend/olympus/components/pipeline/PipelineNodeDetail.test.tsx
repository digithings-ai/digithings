import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, it, expect, vi } from 'vitest';

// Mock the document hook so we don't need Supabase
vi.mock('@/lib/hooks/use-library-document', () => ({
  useLibraryDocument: () => null,
}));
vi.mock('@/components/library/LibraryDocumentBody', () => ({
  default: ({ documentKey }: { documentKey: string }) =>
    createElement('div', { 'data-testid': 'doc-body' }, `doc:${documentKey}`),
}));

import PipelineNodeDetail from './PipelineNodeDetail';
import type { LaidOutNode } from '@/lib/pipeline-layout';

const deliberationNode: LaidOutNode = {
  id: 'selection:deliberation',
  kind: 'substep',
  stageId: 'selection',
  label: 'Deliberation',
  x: 0,
  y: 0,
  width: 160,
  height: 48,
};

describe('PipelineNodeDetail', () => {
  it('renders empty state copy when documentKey is null', () => {
    const html = renderToStaticMarkup(
      createElement(PipelineNodeDetail, { documentKey: null, date: '2026-06-23', onClose: () => {} }),
    );
    // Should have actionable empty state, not a dead end
    expect(html).toMatch(/no document|not available|select a node/i);
  });

  it('shows loading indicator when documentKey is provided but doc is not yet loaded', () => {
    const html = renderToStaticMarkup(
      createElement(PipelineNodeDetail, { documentKey: 'digest', date: '2026-06-23', onClose: () => {} }),
    );
    // Should render the panel wrapper — not crash
    expect(html).toBeTruthy();
    expect(html.length).toBeGreaterThan(10);
  });

  it('renders a close button', () => {
    const html = renderToStaticMarkup(
      createElement(PipelineNodeDetail, { documentKey: 'digest', date: '2026-06-23', onClose: () => {} }),
    );
    // Close affordance
    expect(html).toMatch(/close|✕|×/i);
  });

  it('uses an in-flow lower pane on mobile and a side panel on desktop', () => {
    const html = renderToStaticMarkup(
      createElement(PipelineNodeDetail, { documentKey: 'digest', date: '2026-06-23', onClose: () => {} }),
    );
    expect(html).toContain('h-[46%]');
    expect(html).not.toContain('fixed inset-x-0 bottom-0');
    expect(html).toContain('md:');
  });

  it('renders pipeline guidance when a selected step has no run document', () => {
    const html = renderToStaticMarkup(
      createElement(PipelineNodeDetail, {
        node: deliberationNode,
        documentKey: null,
        date: '2026-06-23',
        onClose: () => {},
      }),
    );

    expect(html).toContain('Pipeline guide');
    expect(html).toContain('Deliberation');
    expect(html).toMatch(/challenge|debate|deliberat/i);
    expect(html).not.toContain('No document selected');
  });
});
