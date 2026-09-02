import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import PipelineArtifactLedger from './PipelineArtifactLedger';

describe('PipelineArtifactLedger', () => {
  it('lists mapped and unmapped persisted artifacts as selectable documents', () => {
    const html = renderToStaticMarkup(
      createElement(PipelineArtifactLedger, {
        artifacts: [
          {
            documentKey: 'macro',
            title: 'Macro view',
            docType: null,
            phase: null,
            category: 'macro',
            segment: 'macro',
            sector: null,
            runType: 'delta',
          },
          {
            documentKey: 'document-deltas/macro',
            title: 'Macro change',
            docType: 'Document Delta',
            phase: null,
            category: 'delta',
            segment: 'document_delta',
            sector: null,
            runType: 'delta',
          },
        ],
        date: '2026-08-05',
        selectedDocumentKey: null,
        onSelect: () => {},
        onClose: () => {},
      })
    );

    expect(html).toContain('All artifacts');
    expect(html).toContain('2 persisted outputs');
    expect(html).toContain('Macro view');
    expect(html).toContain('document-deltas/macro');
    expect(html).toContain('Document Delta');
    expect(html.match(/<button/g)).toHaveLength(3);
  });
});