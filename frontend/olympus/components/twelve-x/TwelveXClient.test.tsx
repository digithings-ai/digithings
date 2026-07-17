import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { TWELVE_X_TABS, TwelveXUnavailable, resolveTab } from './TwelveXClient';
import type { TwelveXTab } from './context';

/* ----------------------------------------------------------------------- */
/* The workspace tab set (final 5-tab redesign — NO Ledger)                */
/* ----------------------------------------------------------------------- */

describe('TwelveXClient tab set', () => {
  it('exposes exactly five tabs', () => {
    expect(TWELVE_X_TABS).toHaveLength(5);
  });

  it('is the canonical Today / Consensus / Intelligence / Matrix / Events set', () => {
    expect(TWELVE_X_TABS.map((t) => t.id)).toEqual([
      'today',
      'consensus',
      'intelligence',
      'matrix',
      'events',
    ]);
  });

  it('has NO ledger tab', () => {
    expect(TWELVE_X_TABS.some((t) => t.id === ('ledger' as TwelveXTab))).toBe(false);
    expect(TWELVE_X_TABS.some((t) => t.label.toLowerCase() === 'ledger')).toBe(false);
  });

  it('labels each tab', () => {
    const labels = Object.fromEntries(TWELVE_X_TABS.map((t) => [t.id, t.label]));
    expect(labels).toMatchObject({
      today: 'Today',
      consensus: 'Consensus',
      intelligence: 'Intelligence',
      matrix: 'Matrix',
      events: 'Events',
    });
  });
});

/* ----------------------------------------------------------------------- */
/* resolveTab — the deep-link / initial-tab seam                           */
/* ----------------------------------------------------------------------- */

describe('resolveTab', () => {
  it('routes each of the five tab params to its tab', () => {
    expect(resolveTab('today')).toBe('today');
    expect(resolveTab('consensus')).toBe('consensus');
    expect(resolveTab('intelligence')).toBe('intelligence');
    expect(resolveTab('matrix')).toBe('matrix');
    expect(resolveTab('events')).toBe('events');
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
  it('keeps the five-tab workspace visible when the feed fails', () => {
    const html = renderToStaticMarkup(createElement(TwelveXUnavailable, { configured: true }));
    expect(html).toContain('FX research is temporarily unavailable');
    expect(html).toContain('Retry');
    for (const { label } of TWELVE_X_TABS) expect(html).toContain(label);
  });

  it('uses presentation-safe copy when the feed is not configured', () => {
    const html = renderToStaticMarkup(createElement(TwelveXUnavailable, { configured: false }));
    expect(html).toContain('FX research is not connected');
    expect(html).not.toContain('NEXT_PUBLIC_');
  });
});
