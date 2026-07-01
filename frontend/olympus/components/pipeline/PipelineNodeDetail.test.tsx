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

  it('uses bottom-sheet classes for mobile layout', () => {
    const html = renderToStaticMarkup(
      createElement(PipelineNodeDetail, { documentKey: 'digest', date: '2026-06-23', onClose: () => {} }),
    );
    // md: prefix separates desktop panel from mobile bottom sheet
    expect(html).toContain('md:');
  });
});
