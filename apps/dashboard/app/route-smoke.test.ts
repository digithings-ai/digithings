import { describe, expect, it } from 'vitest';
import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { join, relative } from 'node:path';

/**
 * Route smoke test — every dashboard route must produce a real static-export
 * artifact with the app shell. Covers all ~24 routes (plan §11 Q2 gate).
 *
 * Runs against `apps/dashboard/out/` (produced by `next build --webpack`). When
 * the export is absent (plain `npm run test` before a build) the suite skips
 * rather than failing — the build gate runs it with the export present.
 */

const root = join(__dirname, '..');
const outDir = join(root, 'out');

function pageRoutes(): string[] {
  const appDir = join(root, 'app');
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

const ROUTES = pageRoutes();
const AUTH_ROUTES = new Set(['/login', '/signup', '/auth/callback']);

const artifact = (route: string) =>
  route === '/' ? join(outDir, 'index.html') : join(outDir, route.slice(1), 'index.html');

describe.skipIf(!existsSync(outDir))('static export route smoke', () => {
  it('covers the ~24 dashboard routes', () => {
    expect(ROUTES.length).toBeGreaterThanOrEqual(24);
  });

  it('every route emits an index.html artifact', () => {
    const missing = ROUTES.filter((r) => !existsSync(artifact(r)));
    expect(missing, `routes with no artifact:\n${missing.join('\n')}`).toEqual([]);
  });

  it('every artifact is a real document carrying the app title', () => {
    for (const route of ROUTES) {
      const html = readFileSync(artifact(route), 'utf8');
      expect(html, route).toContain('<!DOCTYPE html');
      expect(html, route).toContain('digiquant');
    }
  });

  it('every non-auth route renders the shell (sidebar landmark)', () => {
    const missing: string[] = [];
    for (const route of ROUTES) {
      if (AUTH_ROUTES.has(route)) continue;
      const html = readFileSync(artifact(route), 'utf8');
      if (!html.includes('id="app-sidebar-nav"')) missing.push(route);
    }
    expect(missing, `routes missing the shell:\n${missing.join('\n')}`).toEqual([]);
  });

  it('every content route owns exactly one <main> and never nests it', () => {
    for (const route of ROUTES) {
      if (AUTH_ROUTES.has(route)) continue;
      const html = readFileSync(artifact(route), 'utf8');
      const opens = (html.match(/<main[\s>]/g) ?? []).length;
      // Redirect routes render the loader inside the shell's single <main>;
      // content routes also render exactly one. Two would mean a nested
      // landmark (the Q3 regression).
      expect(opens, `${route} has ${opens} <main> landmarks`).toBe(1);
    }
  });

  it('no page nests a second <main> inside its own content', () => {
    // The shell owns the sole landmark; a page must never open its own.
    for (const route of ROUTES) {
      if (AUTH_ROUTES.has(route)) continue;
      const html = readFileSync(artifact(route), 'utf8');
      expect(html, route).not.toMatch(/<main[\s>][\s\S]*<main[\s>]/);
    }
  });
});
