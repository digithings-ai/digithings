import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

vi.mock('next/link', () => ({
  default: (p: { href?: string; children?: import('react').ReactNode; className?: string }) =>
    createElement('a', { href: p.href, className: p.className }, p.children),
}));

import { BookPanel, CorpusPanel, ProfilePanel } from './HousePanels';
import { buildBookView, buildCorpusView, buildProfileView } from '@/lib/house-view';
import type { Doc, Position } from '@/lib/types';

const docs = [
  { id: 'a', date: '2026-09-01', title: 't', type: null, phase: null, category: 'macro', segment: null, sector: null, runType: 'baseline', path: 'theme:ai' },
  { id: 'b', date: '2026-08-31', title: 't', type: null, phase: null, category: 'macro', segment: null, sector: null, runType: 'delta', path: 'x.md' },
] as Doc[];
const positions = [
  { ticker: 'SPY', name: 'S', type: 'LONG', weight_actual: 40, category: 'Equity' },
  { ticker: 'TLT', name: 'T', type: 'LONG', weight_actual: 20, category: 'Rates' },
] as Position[];

describe('HousePanels', () => {
  it('corpus panel renders charts with text summaries and keeps its testid', () => {
    const html = renderToStaticMarkup(createElement(CorpusPanel, { view: buildCorpusView(docs) }));
    expect(html).toContain('data-testid="house-corpus-panel"');
    expect(html).toContain('data-slot="calendar-heatmap"');
    expect(html).toContain('2 docs from');
    expect(html).toContain('Run mix: 1 baseline, 1 delta');
    expect(html).toContain('theme:ai');
  });

  it('corpus panel fails soft to an error empty state when the source is down', () => {
    const html = renderToStaticMarkup(
      createElement(CorpusPanel, { view: buildCorpusView(null), unavailable: 'Data source unreachable.' })
    );
    expect(html).toContain('Corpus unavailable');
    expect(html).not.toContain('calendar-heatmap');
  });

  it('book panel renders treemap, sleeve bar and em dash for missing NAV', () => {
    const html = renderToStaticMarkup(
      createElement(BookPanel, { view: buildBookView(positions, [], 40) })
    );
    expect(html).toContain('data-testid="house-book-panel"');
    expect(html).toContain('data-slot="treemap"');
    expect(html).toContain('Equity 40%');
    expect(html).toContain('Cash');
    expect(html).toContain('—');
    expect(html).toContain('/portfolio/ledger');
  });

  it('profile panel stays read-only and renders the tier matrix', () => {
    const html = renderToStaticMarkup(
      createElement(ProfilePanel, { view: buildProfileView(positions, { max_position: 15 }) })
    );
    expect(html).toContain('data-testid="house-profile-panel"');
    expect(html).toContain('read-only');
    expect(html).toContain('data-slot="heat-grid"');
    expect(html).toContain('max_position');
    expect(html).not.toMatch(/<(input|button)/);
  });
});
