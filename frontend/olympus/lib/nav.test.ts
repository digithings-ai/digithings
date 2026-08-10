import { describe, it, expect, vi } from 'vitest';
import { NAV, isDbExempt } from './nav';

describe('NAV', () => {
  it('is the 5-destination owner spine, in order (FX Hub permanent since #1664)', () => {
    expect(NAV.map((n) => n.href)).toEqual(['/', '/portfolio', '/pipeline', '/twelve-x', '/system']);
    expect(NAV.map((n) => n.label)).toEqual(['Brief', 'Portfolio', 'Pipeline', 'FX Hub', 'System']);
    expect(NAV.find((n) => n.href === '/twelve-x')?.demoted).toBeUndefined();
  });

  it('demotes only System', () => {
    expect(NAV.filter((n) => n.demoted).map((n) => n.href)).toEqual(['/system']);
  });

  it('gives every item a renderable icon', () => {
    expect(NAV.every((n) => typeof n.icon === 'function' || typeof n.icon === 'object')).toBe(true);
  });
});

describe('isDbExempt', () => {
  it('exempts operator + static-redirect routes while the backend is down', () => {
    expect(isDbExempt('/system')).toBe(true);
    expect(isDbExempt('/settings')).toBe(true);
    expect(isDbExempt('/architecture')).toBe(true);
    expect(isDbExempt('/library')).toBe(true);
    expect(isDbExempt('/observability')).toBe(true);
    expect(isDbExempt('/performance')).toBe(true);
    expect(isDbExempt('/research')).toBe(true);
    expect(isDbExempt('/strategy')).toBe(true);
    expect(isDbExempt('/portfolio/theses')).toBe(true);
    // twelve-x gates itself on its own research feed, not the main backend (#1664)
    expect(isDbExempt('/twelve-x')).toBe(true);
  });

  it('matches nested paths under an exempt prefix', () => {
    expect(isDbExempt('/system/how-it-works')).toBe(true);
    expect(isDbExempt('/settings/anything')).toBe(true);
  });

  it('gates the data-backed surfaces', () => {
    expect(isDbExempt('/')).toBe(false);
    expect(isDbExempt('/portfolio')).toBe(false);
    expect(isDbExempt('/pipeline')).toBe(false);
    expect(isDbExempt('/why')).toBe(false);
  });

  it('does not treat a prefix substring as a match', () => {
    // '/systematic' is not under '/system'
    expect(isDbExempt('/systematic')).toBe(false);
    // '/portfolio' must stay gated even though '/portfolio/theses' is exempt
    expect(isDbExempt('/portfolio')).toBe(false);
  });

  it('handles null / undefined pathnames defensively', () => {
    expect(isDbExempt(null)).toBe(false);
    expect(isDbExempt(undefined)).toBe(false);
  });
});
