import { describe, expect, it } from 'vitest';
import { shouldShowDocumentArchive } from './document-archive-gate';
import type { Doc } from './types';

function doc(date: string, id: string): Doc {
  return {
    id,
    date,
    title: '',
    type: null,
    phase: null,
    category: null,
    segment: null,
    sector: null,
    runType: null,
    path: `analyst/${id}`,
  };
}

describe('shouldShowDocumentArchive (faceted archive deferral gate)', () => {
  it('is false on the baseline single-day world (archive stays absent)', () => {
    expect(shouldShowDocumentArchive([doc('2026-06-23', 'a'), doc('2026-06-23', 'b')])).toBe(false);
  });
  it('is false with no documents', () => {
    expect(shouldShowDocumentArchive([])).toBe(false);
  });
  it('un-defers once documents span more than one distinct date', () => {
    expect(shouldShowDocumentArchive([doc('2026-06-23', 'a'), doc('2026-06-24', 'b')])).toBe(true);
  });
  it('ignores docs with no date when counting distinct dates', () => {
    const noDate = doc('', 'c');
    expect(shouldShowDocumentArchive([doc('2026-06-23', 'a'), noDate])).toBe(false);
  });
});
