import { describe, it, expect } from 'vitest';
import {
  NAV,
  DB_EXEMPT_PREFIXES,
  LEGACY_REDIRECTS,
  isDbExempt,
  isLegacyRedirectPath,
  navItemForPath,
} from './nav';

describe('NAV', () => {
  it('is the 4-destination owner spine + FX Hub (System removed)', () => {
    expect(NAV.map((n) => n.href)).toEqual(['/', '/portfolio', '/pipeline', '/twelve-x']);
    expect(NAV.map((n) => n.label)).toEqual(['Brief', 'Portfolio', 'Pipeline', 'FX Hub']);
    expect(NAV.find((n) => n.href === '/system')).toBeUndefined();
  });

  it('has no demoted footnote items', () => {
    expect(NAV.filter((n) => n.demoted)).toEqual([]);
  });

  it('gives every item a renderable icon', () => {
    expect(NAV.every((n) => typeof n.icon === 'function' || typeof n.icon === 'object')).toBe(true);
  });
});

describe('DB_EXEMPT_PREFIXES (the gate allowlist, enumerated exactly)', () => {
  it('is exactly the explicit operator/own-feed/static set — no more, no less', () => {
    expect([...DB_EXEMPT_PREFIXES].sort()).toEqual(
      ['/pipeline', '/settings', '/twelve-x', '/house', '/portfolio/theses'].sort()
    );
  });

  it('exempts the effective set: explicit prefixes + every legacy redirect', () => {
    const effective = [
      ...DB_EXEMPT_PREFIXES,
      ...Object.keys(LEGACY_REDIRECTS),
    ];
    for (const path of effective) {
      expect(isDbExempt(path), path).toBe(true);
    }
    // /pipeline is the one the comment always claimed but the list dropped.
    expect(isDbExempt('/pipeline')).toBe(true);
    // A redirect route not in the explicit list is still exempt by derivation.
    expect(isDbExempt('/portfolio/period')).toBe(true);
  });

  it('matches nested paths under an exempt prefix', () => {
    expect(isDbExempt('/settings/anything')).toBe(true);
    expect(isDbExempt('/pipeline/whatif')).toBe(true);
    expect(isDbExempt('/twelve-x/trades')).toBe(true);
  });

  it('gates the data-backed surfaces', () => {
    for (const path of ['/', '/portfolio', '/portfolio/ledger', '/portfolio/tickers', '/why']) {
      expect(isDbExempt(path), path).toBe(false);
    }
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

describe('LEGACY_REDIRECTS', () => {
  it('is the served-but-redirecting set, and no target is itself a redirect', () => {
    expect(Object.keys(LEGACY_REDIRECTS).sort()).toEqual(
      [
        '/architecture',
        '/library',
        '/observability',
        '/performance',
        '/portfolio/period',
        '/research',
        '/strategy',
        '/system',
      ].sort()
    );
    for (const [from, to] of Object.entries(LEGACY_REDIRECTS)) {
      const bare = to.split('?')[0];
      expect(isLegacyRedirectPath(bare), `${from} → ${to} chains to a redirect`).toBe(false);
    }
  });

  it('identifies redirect pathnames only (not their targets)', () => {
    expect(isLegacyRedirectPath('/system')).toBe(true);
    expect(isLegacyRedirectPath('/system/')).toBe(true);
    expect(isLegacyRedirectPath('/pipeline')).toBe(false);
    expect(isLegacyRedirectPath('/systematic')).toBe(false);
    expect(isLegacyRedirectPath(null)).toBe(false);
  });
});

describe('navItemForPath (the nav → route map)', () => {
  it('every nav destination resolves to itself', () => {
    for (const { href } of NAV) {
      expect(navItemForPath(href), href).toBe(href);
    }
  });

  it('keeps family routes on their parent destination', () => {
    expect(navItemForPath('/portfolio/ledger')).toBe('/portfolio');
    expect(navItemForPath('/portfolio/performance')).toBe('/portfolio');
    expect(navItemForPath('/portfolio/tickers')).toBe('/portfolio');
    expect(navItemForPath('/twelve-x')).toBe('/twelve-x');
  });

  it('does NOT collapse a live non-destination route onto Pipeline', () => {
    // /why is a live route (components/why/why-client) with its own page — the
    // old hard-coded regex highlighted Pipeline here. It must resolve to null.
    expect(navItemForPath('/why')).toBeNull();
    expect(navItemForPath('/settings')).toBeNull();
    expect(navItemForPath('/house')).toBeNull();
  });

  it('resolves a legacy redirect to the destination it redirects to', () => {
    for (const path of ['/system', '/research', '/library', '/observability', '/architecture']) {
      expect(navItemForPath(path), path).toBe('/pipeline');
    }
    expect(navItemForPath('/performance')).toBe('/portfolio');
    expect(navItemForPath('/strategy')).toBe('/portfolio');
    expect(navItemForPath('/portfolio/theses')).toBe('/portfolio');
  });

  it('strips a basePath before resolving', () => {
    expect(navItemForPath('/dashboard/portfolio', '/dashboard')).toBe('/portfolio');
    expect(navItemForPath('/dashboard', '/dashboard')).toBe('/');
    expect(navItemForPath('/dashboard/pipeline', '/dashboard')).toBe('/pipeline');
  });

  it('handles null / undefined defensively', () => {
    expect(navItemForPath(null)).toBeNull();
    expect(navItemForPath(undefined)).toBeNull();
  });
});
