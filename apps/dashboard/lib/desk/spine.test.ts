import { describe, expect, it } from 'vitest';
import {
  DESK_OPTIONS,
  DESK_PATH_JUMPS,
  formatChromePath,
  HOUSE_SPINE,
  locationChrome,
  railForDesk,
  railLabels,
} from './spine';

describe('desk spine', () => {
  it('lists house, rates watch, and FX Hub', () => {
    expect(DESK_OPTIONS.map((desk) => desk.label)).toEqual(['house', 'rates watch', 'FX Hub']);
    expect(DESK_OPTIONS.find((desk) => desk.id === 'rates-watch')?.badge).toBe('wip');
  });

  it('nests portfolio children and omits Corpus / Book / Profile', () => {
    const labels = railLabels(HOUSE_SPINE);
    expect(labels).toEqual(expect.arrayContaining(['holdings', 'theses', 'tearsheet', 'ledger', 'attribution']));
    expect(labels).not.toContain('Corpus');
    expect(labels).not.toContain('Profile');
    const portfolio = HOUSE_SPINE.find((node) => node.id === 'portfolio');
    expect(portfolio?.children?.map((child) => child.href)).toEqual([
      '/portfolio',
      '/portfolio?tab=theses',
      '/portfolio/performance',
      '/portfolio/ledger',
      '/portfolio/attribution',
    ]);
  });

  it('marks rates watch and unfinished tools with an honest banner', () => {
    const rates = railForDesk('rates-watch');
    expect(rates.every((node) => node.badge === 'wip' && node.banner)).toBe(true);
    expect(rates.map((node) => node.label)).toEqual(['digest', 'watchlist', 'theses', 'run', 'config']);
    const terminal = HOUSE_SPINE.find((node) => node.id === 'tools')?.children?.find(
      (node) => node.id === 'terminal',
    );
    expect(terminal?.badge).toBe('soon');
    expect(terminal?.banner?.body).toMatch(/does not embed a vendor terminal/);
    const strategies = HOUSE_SPINE.find((node) => node.id === 'strategies');
    expect(strategies?.badge).toBe('wip');
    expect(strategies?.banner?.body).toMatch(/does not|Nothing here places an order/);
  });

  it('limits an fx-hub-only invitee to the FX spine', () => {
    const labels = railLabels(railForDesk('house', true));
    expect(labels).toContain('today');
    expect(labels).not.toContain('holdings');
    expect(labels).not.toContain('Corpus');
  });
});

describe('locationChrome', () => {
  it('reads house / portfolio / holdings on the holdings route', () => {
    expect(formatChromePath(locationChrome('/portfolio').segments)).toBe(
      'house / portfolio / holdings',
    );
    expect(formatChromePath(locationChrome('/portfolio', '?tab=holdings').segments)).toBe(
      'house / portfolio / holdings',
    );
    expect(formatChromePath(locationChrome('/portfolio/performance').segments)).toBe(
      'house / portfolio / tearsheet',
    );
    expect(formatChromePath(locationChrome('/portfolio', '?tab=theses').segments)).toBe(
      'house / portfolio / theses',
    );
  });

  it('treats /house as the brief desk, not Corpus / Book / Profile', () => {
    const chrome = locationChrome('/house');
    expect(formatChromePath(chrome.segments)).toBe('house / brief');
    expect(chrome.segments.some((segment) => /corpus|profile/i.test(segment.label))).toBe(false);
  });

  it('shows a rates-watch banner instead of a blank page', () => {
    const chrome = locationChrome('/', '?desk=rates-watch&section=watchlist');
    expect(formatChromePath(chrome.segments)).toBe('rates watch / watchlist');
    expect(chrome.banner?.badge).toBe('wip');
    expect(chrome.banner?.body).toMatch(/not a second book/);
  });

  it('aliases brief panes without inventing /book or /movers routes', () => {
    const movers = locationChrome('/', '?pane=movers');
    expect(formatChromePath(movers.segments)).toBe('house / brief / movers');
    expect(movers.segments[2]?.href.startsWith('/movers')).toBe(false);
    const gloom = locationChrome('/', '?pane=gloomberg');
    expect(gloom.banner?.badge).toBe('soon');
    expect(formatChromePath(locationChrome('/pipeline').segments)).toBe('house / pipeline');
  });

  it('exposes palette jumps for those paths', () => {
    expect(DESK_PATH_JUMPS.map((item) => item.title)).toContain('house / portfolio / holdings');
    expect(DESK_PATH_JUMPS.find((item) => item.id === 'go-house')).toMatchObject({ href: '/' });
  });
});
