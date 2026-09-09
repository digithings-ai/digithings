import { describe, expect, it } from 'vitest';
import {
  categorizeResearchDoc,
  isKnowledgeBaseDoc,
  isDailyResearchDoc,
  RESEARCH_CATEGORY_ORDER,
} from './research-doc-categorize';
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

describe('research-doc-categorize (retained for future faceted archive)', () => {
  it('routes the digest to Digest', () => {
    expect(categorizeResearchDoc(doc({ path: 'digest' }))).toBe('Digest');
  });
  it('routes per-ticker analyst docs to Intelligence', () => {
    expect(categorizeResearchDoc(doc({ path: 'analyst/EWT' }))).toBe('Intelligence');
  });
  it('routes macro/asset-class segments to Market Analysis', () => {
    expect(categorizeResearchDoc(doc({ path: 'macro', segment: 'macro' }))).toBe('Market Analysis');
  });
  it('marks deep dives as knowledge-base docs, daily research otherwise', () => {
    const deepDive = doc({ path: 'research/deep-dives/ai-capex', category: 'deep-dive' });
    expect(isKnowledgeBaseDoc(deepDive)).toBe(true);
    expect(isDailyResearchDoc(deepDive)).toBe(false);
    expect(isDailyResearchDoc(doc({ path: 'digest' }))).toBe(true);
  });
  it('keeps Digest first in the category order', () => {
    expect(RESEARCH_CATEGORY_ORDER[0]).toBe('Digest');
  });
});
