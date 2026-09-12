import { describe, expect, it } from 'vitest';
import { buildDocumentSearchItems } from './document-search';
import type { Doc } from './types';

function doc(partial: Partial<Doc>): Doc {
  return {
    id: 'x',
    date: '2026-06-23',
    title: '',
    type: null,
    phase: null,
    category: null,
    segment: null,
    sector: null,
    runType: null,
    path: '',
    ...partial,
  };
}

describe('buildDocumentSearchItems', () => {
  const docs: Doc[] = [
    doc({ id: '1', path: 'analyst/EWT', title: 'EWT analyst', date: '2026-06-23', segment: 'analyst' }),
    doc({ id: '2', path: 'deliberation/IJR', title: 'IJR deliberation', date: '2026-06-23', segment: 'deliberation' }),
    doc({ id: '3', path: 'sector-tech', title: 'Technology sector', date: '2026-06-23', segment: 'sector', sector: 'tech' }),
    doc({ id: '4', path: 'macro', title: 'Macro outlook', date: '2026-06-23', segment: 'macro' }),
  ];

  it('returns nothing for a blank query (search is keyed, not a dump)', () => {
    expect(buildDocumentSearchItems(docs, '')).toEqual([]);
    expect(buildDocumentSearchItems(docs, '   ')).toEqual([]);
  });

  it('matches a ticker against the document_key (path) case-insensitively', () => {
    const out = buildDocumentSearchItems(docs, 'ewt');
    expect(out).toHaveLength(1);
    expect(out[0].id).toBe('doc-1');
    // Deep-links to the Pipeline node via the locked grammar (node = document_key, url-encoded).
    expect(out[0].href).toContain('/pipeline?');
    expect(out[0].href).toContain('date=2026-06-23');
    expect(out[0].href).toContain('node=analyst%2FEWT');
    // analyst/* maps to the selection stage (stageForDocumentKey contract).
    expect(out[0].href).toContain('stage=selection');
  });

  it('matches a segment word across multiple docs', () => {
    const out = buildDocumentSearchItems(docs, 'sector');
    expect(out.map((i) => i.id)).toContain('doc-3');
  });

  it('matches against the title', () => {
    const out = buildDocumentSearchItems(docs, 'outlook');
    expect(out.map((i) => i.id)).toEqual(['doc-4']);
  });

  it('ranks document_key-prefix matches above mid-string matches', () => {
    const mixed: Doc[] = [
      doc({ id: 'a', path: 'sector-tech', title: 'Technology', segment: 'sector' }),
      doc({ id: 'b', path: 'analyst/SECTORS-ETF', title: 'Sectors ETF analyst', segment: 'analyst' }),
    ];
    const out = buildDocumentSearchItems(mixed, 'sector');
    expect(out[0].id).toBe('doc-a'); // path starts with the query
  });

  it('carries date + stage provenance in the hint', () => {
    const out = buildDocumentSearchItems(docs, 'macro');
    expect(out[0].hint).toContain('2026-06-23');
    expect(out[0].hint.toLowerCase()).toContain('research'); // macro → research stage
  });

  it('honors the limit', () => {
    const many: Doc[] = Array.from({ length: 20 }, (_, i) =>
      doc({ id: String(i), path: `analyst/T${i}`, title: `T${i} analyst`, segment: 'analyst' })
    );
    expect(buildDocumentSearchItems(many, 'analyst', 5)).toHaveLength(5);
  });
});
