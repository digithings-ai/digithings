import { describe, it, expect } from 'vitest';
import { buildCommandItems, buildTickerCommandItems, filterCommandItems } from './command-palette';
import type { Doc } from '@/lib/types';

const data = {
  portfolio: { strategy: { theses: [{ id: 'MT1', name: 'Small caps' }] } },
  docs: [
    { date: '2026-06-23', title: 'Digest', path: 'digest' },
    { date: '2026-06-23', title: 'IJR analyst', path: 'analyst/IJR' },
    { date: '2026-06-22', title: 'Energy sector', path: 'sector-energy' },
  ],
} as unknown as Parameters<typeof buildCommandItems>[0];

describe('buildCommandItems (F2 palette — static rows only)', () => {
  it('ships no legacy Why entries and points the read at the Pipeline grammar', () => {
    const items = buildCommandItems(data);
    expect(items.some((i) => i.title.startsWith('Why'))).toBe(false);
    const read = items.find((i) => i.id === 'go-pipeline-read')!;
    expect(read.href).toContain('/pipeline?');
    expect(read.href).toContain('node=digest');
  });
  it('does NOT bake document hits into the static list (those are query-gated)', () => {
    const items = buildCommandItems(data);
    expect(items.some((i) => i.id.startsWith('doc-'))).toBe(false);
  });
});

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

const baseItems = [
  { id: 'go-today', title: 'Brief', hint: 'Dashboard home', href: '/', icon: () => null },
  { id: 'go-pipeline', title: 'Pipeline', hint: 'Daily decision graph', href: '/pipeline', icon: () => null },
] as Parameters<typeof filterCommandItems>[0];

const docs: Doc[] = [doc({ id: '1', path: 'analyst/EWT', title: 'EWT analyst', segment: 'analyst' })];

describe('buildTickerCommandItems (#1562 PR2 — Tickers palette group)', () => {
  it('maps each ticker to its dossier route', () => {
    const items = buildTickerCommandItems(['XLE', 'QQQ']);
    expect(items).toHaveLength(2);
    expect(items[0]).toMatchObject({ id: 'ticker-XLE', title: 'XLE', href: '/portfolio/tickers?ticker=XLE' });
    expect(items[1].href).toBe('/portfolio/tickers?ticker=QQQ');
  });

  it('is query-filterable through filterCommandItems like any other group', () => {
    const items = buildTickerCommandItems(['XLE', 'QQQ', 'IWM']);
    const out = filterCommandItems(items, [], 'xle');
    expect(out.map((i) => i.title)).toEqual(['XLE']);
  });
});

describe('filterCommandItems', () => {
  it('returns the static list unchanged for a blank query (no doc dump)', () => {
    expect(filterCommandItems(baseItems, docs, '')).toEqual(baseItems);
  });
  it('appends matching document hits after static matches', () => {
    const out = filterCommandItems(baseItems, docs, 'ewt');
    const docHit = out.find((i) => i.id === 'doc-1');
    expect(docHit).toBeTruthy();
    expect(docHit!.href).toContain('/pipeline?');
    expect(docHit!.href).toContain('node=analyst%2FEWT');
  });
  it('keeps static nav matches ahead of document hits', () => {
    const out = filterCommandItems(baseItems, docs, 'pipeline');
    expect(out[0].id).toBe('go-pipeline');
  });
});
