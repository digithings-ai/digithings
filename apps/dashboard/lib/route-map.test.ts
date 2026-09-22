import { describe, expect, it } from 'vitest';
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { join, relative } from 'node:path';
import { LEGACY_REDIRECTS, NAV, isLegacyRedirectPath } from './nav';

/**
 * The nav → route map (plan §6/§8, "route integrity"): every advertised
 * destination must resolve to itself, and no advertised destination may be a
 * route that silently client-redirects (the route-collapse regression). This
 * test is derived from the filesystem, so it fails the moment a destination is
 * pointed at a redirect or a dead route — not just when this list changes.
 */

const root = join(__dirname, '..');
const appDir = join(root, 'app');
const read = (rel: string) => readFileSync(join(root, rel), 'utf8');

/** Every `app/**\/page.tsx`, as an app-relative route (`/portfolio/ledger`). */
function pageRoutes(): string[] {
  const out: string[] = [];
  const walk = (dir: string) => {
    for (const e of readdirSync(dir, { withFileTypes: true })) {
      const p = join(dir, e.name);
      if (e.isDirectory()) walk(p);
      else if (e.name === 'page.tsx') {
        const rel = relative(appDir, dir).split('\\').join('/');
        out.push(rel ? `/${rel}` : '/');
      }
    }
  };
  walk(appDir);
  return out.sort();
}

/** Routes whose page default-exports the shared client redirect. */
function redirectRoutes(): string[] {
  return pageRoutes().filter((route) =>
    read(join('app', route === '/' ? '' : route.slice(1), 'page.tsx')).includes(
      '@/components/legacy-spa-redirect'
    )
  );
}

/** Non-test .ts/.tsx sources under app/ + components/. */
function uiSources(): string[] {
  const out: string[] = [];
  const walk = (dir: string) => {
    for (const e of readdirSync(dir, { withFileTypes: true })) {
      const p = join(dir, e.name);
      if (e.isDirectory()) walk(p);
      else if (/\.tsx?$/.test(e.name) && !/\.test\.tsx?$/.test(e.name)) {
        out.push(relative(root, p).split('\\').join('/'));
      }
    }
  };
  walk(appDir);
  walk(join(root, 'components'));
  return out;
}

/** Normalize an internal href to a route, or null when it is not static-internal. */
function routeOf(href: string): string | null {
  if (!href.startsWith('/')) return null; // external / mailto / relative
  const bare = href.split(/[?#]/)[0];
  const stripped = bare.startsWith('/dashboard/') ? bare.slice('/dashboard'.length) : bare;
  return stripped.replace(/\/+$/, '') || '/';
}

const ROUTES = pageRoutes();
const REDIRECTS = redirectRoutes();

describe('dashboard route map (derived from app/)', () => {
  it('serves the ~24 dashboard routes', () => {
    expect(ROUTES.length).toBeGreaterThanOrEqual(24);
    // A few anchors the smoke test also relies on.
    for (const r of ['/', '/portfolio', '/pipeline', '/twelve-x', '/why', '/settings']) {
      expect(ROUTES, r).toContain(r);
    }
  });

  it('the redirect registry matches the routes that actually redirect', () => {
    // If a page starts/stops client-redirecting, or the registry drifts, this
    // fails. That is the invariant the route-collapse fix rests on.
    expect(REDIRECTS.sort()).toEqual(Object.keys(LEGACY_REDIRECTS).sort());
  });

  it('every legacy redirect route is actually served', () => {
    for (const route of REDIRECTS) {
      expect(ROUTES, route).toContain(route);
    }
  });

  it('every NAV destination resolves to itself and is not a redirect', () => {
    for (const { href } of NAV) {
      expect(ROUTES, `${href} is not a route`).toContain(href);
      expect(isLegacyRedirectPath(href), `${href} is a redirect destination`).toBe(false);
    }
  });

  it('no static internal href in app/ or components/ points at a dead route', () => {
    // `href="…"` JSX literals and `href: '…'` object literals — the two forms
    // every nav surface uses. Dynamic hrefs (template/handler) are skipped.
    const problems: string[] = [];
    for (const rel of uiSources()) {
      const src = read(rel);
      const literals = [
        ...src.matchAll(/href="([^"]+)"/g),
        ...src.matchAll(/href:\s*'([^']+)'/g),
      ].map((m) => m[1]);
      for (const href of literals) {
        const route = routeOf(href);
        if (route === null) continue;
        if (!ROUTES.includes(route)) problems.push(`${rel}: href="${href}" → ${route}`);
      }
    }
    expect(problems, `dead nav hrefs:\n${problems.join('\n')}`).toEqual([]);
  });

  it('the pages these destinations render exist (page.tsx is on disk)', () => {
    for (const route of ROUTES) {
      const dir = route === '/' ? appDir : join(appDir, route.slice(1));
      expect(existsSync(join(dir, 'page.tsx')), route).toBe(true);
    }
  });
});
