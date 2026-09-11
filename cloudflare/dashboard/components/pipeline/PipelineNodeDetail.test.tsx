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
  it('renders nothing when documentKey is null', () => {
    const html = renderToStaticMarkup(
      createElement(PipelineNodeDetail, { documentKey: null, date: '2026-06-23', onClose: () => {} }),
    );
    expect(html).toBe('');
    expect(html).not.toMatch(/pipeline guide|select a node|no document selected/i);
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

  it('uses a full-page overlay on mobile and a side panel on desktop', () => {
    const html = renderToStaticMarkup(
      createElement(PipelineNodeDetail, { documentKey: 'digest', date: '2026-06-23', onClose: () => {} }),
    );
    expect(html).toContain('fixed inset-0');
    expect(html).toContain('h-dvh');
    expect(html).toContain('md:relative');
    expect(html).toContain('md:w-[min(58vw,680px)]');
    expect(html).not.toContain('h-[46%]');
    expect(html).not.toContain('md:w-[372px]');
  });

  it('does not open a description-only sidebar when a selected step has no document', () => {
    const html = renderToStaticMarkup(
      createElement(PipelineNodeDetail, {
        node: deliberationNode,
        documentKey: null,
        date: '2026-06-23',
        onClose: () => {},
      }),
    );

    expect(html).toBe('');
    expect(html).not.toContain('Pipeline guide');
    expect(html).not.toContain('Stage overview');
  });
});
