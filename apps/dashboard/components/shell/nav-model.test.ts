import { describe, expect, it } from 'vitest';
import { WORKSPACE, activeChildId, childHref, layoutFor, settingsGroup, titleFor } from './nav-model';

const portfolio = WORKSPACE.find((g) => g.id === 'portfolio')!;
const fx = WORKSPACE.find((g) => g.id === 'twelve-x')!;

describe('activeChildId', () => {
  it('defaults to Holdings on /portfolio and Today on /twelve-x', () => {
    expect(activeChildId(portfolio, '/portfolio', '', '')).toBe('holdings');
    expect(activeChildId(fx, '/twelve-x', '', '')).toBe('today');
  });

  it('follows ?tab= and sub-routes', () => {
    expect(activeChildId(portfolio, '/portfolio', '?tab=theses', '')).toBe('theses');
    expect(activeChildId(portfolio, '/portfolio/theses/abc', '', '')).toBe('theses');
    expect(activeChildId(portfolio, '/portfolio/performance', '', '')).toBe('tearsheet');
    expect(activeChildId(portfolio, '/performance', '', '')).toBe('tearsheet');
    expect(activeChildId(portfolio, '/portfolio/attribution', '', '')).toBe('attribution');
    expect(activeChildId(fx, '/twelve-x', '?tab=matrix', '')).toBe('matrix');
  });

  it('returns null off the destination', () => {
    expect(activeChildId(portfolio, '/pipeline', '', '')).toBeNull();
  });

  it('settings children follow the hash and only list granted tabs', () => {
    const free = settingsGroup('free');
    expect(free.children.map((c) => c.id)).not.toContain('brokers');
    expect(free.children.map((c) => c.id)).toContain('billing');
    expect(activeChildId(free, '/settings', '', '#billing')).toBe('billing');
    expect(activeChildId(free, '/settings', '', '')).toBe(free.children[0]?.id);
    expect(settingsGroup(null).children).toEqual([]);
  });
});

describe('childHref / titleFor / layoutFor', () => {
  it('builds query and hash hrefs', () => {
    expect(childHref(portfolio.children[1]!)).toBe('/portfolio?tab=theses');
    expect(childHref(settingsGroup('enterprise').children[0]!)).toMatch(/^\/settings#/);
  });

  it('gives every route a static title and pipeline the canvas layout', () => {
    expect(titleFor('/dashboard/')).toBe('Brief');
    expect(titleFor('/dashboard/portfolio/attribution/')).toBe('Portfolio');
    expect(titleFor('/dashboard/why')).toBe('Pipeline');
    expect(layoutFor('/dashboard/pipeline/')).toBe('canvas');
    expect(layoutFor('/dashboard/settings/')).toBe('contained');
  });
});
