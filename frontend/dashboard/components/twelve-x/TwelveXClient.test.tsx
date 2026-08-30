import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { TWELVE_X_TABS, TwelveXUnavailable, resolveTab } from './TwelveXClient';
import type { TwelveXTab } from './context';

/* ----------------------------------------------------------------------- */
/* The workspace tab set (4 visible tabs — Intelligence merged into Consensus) */
/* ----------------------------------------------------------------------- */

describe('TwelveXClient tab set', () => {
  it('exposes exactly six tabs', () => {
    expect(TWELVE_X_TABS).toHaveLength(6);
  });

  it('is the canonical Today / Consensus / Track record / Matrix / Events / How-it-works set', () => {
    expect(TWELVE_X_TABS.map((t) => t.id)).toEqual([
      'today',
      'consensus',
      'track-record',
      'matrix',
      'events',
      'how-it-works',
    ]);
  });

  it('has NO intelligence or ledger tab in the visible set', () => {
    expect(TWELVE_X_TABS.some((t) => t.id === ('intelligence' as TwelveXTab))).toBe(false);
    expect(TWELVE_X_TABS.some((t) => t.id === ('ledger' as TwelveXTab))).toBe(false);
  });

  it('labels each tab', () => {
    const labels = Object.fromEntries(TWELVE_X_TABS.map((t) => [t.id, t.label]));
    expect(labels).toMatchObject({
      today: 'Today',
      consensus: 'Consensus',
      'track-record': 'Track record',
      matrix: 'Matrix',
      events: 'Events',
      'how-it-works': 'How it works',
    });
  });
});

/* ----------------------------------------------------------------------- */
/* resolveTab — the deep-link / initial-tab seam                           */
/* ----------------------------------------------------------------------- */

describe('resolveTab', () => {
  it('routes each of the six tab params to its tab', () => {
    expect(resolveTab('today')).toBe('today');
    expect(resolveTab('consensus')).toBe('consensus');
    expect(resolveTab('track-record')).toBe('track-record');
    expect(resolveTab('matrix')).toBe('matrix');
    expect(resolveTab('events')).toBe('events');
    expect(resolveTab('how-it-works')).toBe('how-it-works');
  });

  it('redirects legacy intelligence param to consensus', () => {
    expect(resolveTab('intelligence')).toBe('consensus');
  });

  it('defaults to Today for null / unknown params', () => {
    expect(resolveTab(null)).toBe('today');
    expect(resolveTab('')).toBe('today');
    expect(resolveTab('nope')).toBe('today');
  });

  it('no longer resolves the retired ledger param to a ledger tab', () => {
    expect(resolveTab('ledger')).toBe('today');
  });
});

describe('TwelveXUnavailable', () => {
  it('renders a flat error state inside the workspace chrome (tab bar stays with the parent)', () => {
    const html = renderToStaticMarkup(createElement(TwelveXUnavailable, { configured: true }));
    expect(html).toContain('FX research is temporarily unavailable');
    expect(html).toContain('Retry');
    // #1664: the parent workspace owns the command band + tab bar so
    // How-it-works stays reachable while the feed is down; the unavailable
    // state is content-only and flat.
    expect(html).not.toContain('glass-card');
    expect(html).not.toContain('rounded-lg');
    expect(html).toContain('border-hair');
    expect(html).toContain('bg-ink');
    expect(html).toContain('text-bg');
  });

  it('uses presentation-safe copy when the feed is not configured', () => {
    const html = renderToStaticMarkup(createElement(TwelveXUnavailable, { configured: false }));
    expect(html).toContain('FX research is not connected');
    expect(html).not.toContain('NEXT_PUBLIC_');
  });
});

describe('twelve-x utilitarian slabs', () => {
  const sources = readdirSync(__dirname).filter(
    (f) => f.endsWith('.tsx') && !f.endsWith('.test.tsx'),
  );

  it('has no glass-card, rounded-lg, or rounded-xl leftovers in components', () => {
    const offenders: string[] = [];
    for (const f of sources) {
      const s = readFileSync(join(__dirname, f), 'utf8');
      if (/\bglass-card\b|\brounded-lg\b|\brounded-xl\b/.test(s)) offenders.push(f);
    }
    expect(offenders).toEqual([]);
  });
});
