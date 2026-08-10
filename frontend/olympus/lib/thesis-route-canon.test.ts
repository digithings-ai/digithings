import { describe, expect, it } from 'vitest';
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';

/**
 * Thesis detail routing canon (#1760).
 *
 * Olympus ships with `output: 'export'` (`next.config.mjs`), so a `[thesisId]`
 * dynamic segment can only serve the ids `generateStaticParams` enumerated at
 * build time — every thesis the daily pipeline creates after a deploy hard-404s.
 * Production carried five dead links on 2026-08-01 for exactly this reason.
 *
 * The detail view therefore lives at `/portfolio/theses?thesis=<id>` on a single
 * static page, matching the `?ticker=` precedent documented in
 * `app/portfolio/tickers/page.tsx`. This file is the regression guard: it fails
 * if the dynamic segment, its build-time enumeration, or a path-form thesis href
 * comes back.
 */

const root = join(__dirname, '..');

/** Every `.ts`/`.tsx` source under `dir`, recursively (skips `node_modules`). */
function sourceFiles(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === 'node_modules' || entry.name.startsWith('.')) continue;
    const path = join(dir, entry.name);
    if (entry.isDirectory()) {
      out.push(...sourceFiles(path));
    } else if (/\.tsx?$/.test(entry.name)) {
      out.push(path);
    }
  }
  return out;
}

/** Directory names of every route segment under `app/`, recursively. */
function routeSegments(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (!entry.isDirectory()) continue;
    out.push(relative(join(root, 'app'), join(dir, entry.name)));
    out.push(...routeSegments(join(dir, entry.name)));
  }
  return out;
}

describe('thesis detail route canon (#1760)', () => {
  it('has no dynamic route segment — static export cannot enumerate a growing table', () => {
    const dynamic = routeSegments(join(root, 'app')).filter((seg) => seg.includes('['));
    expect(dynamic, `dynamic segments 404 on ids created after the deploy: ${dynamic.join(', ')}`).toEqual([]);
  });

  it('ships no build-time thesis id enumeration', () => {
    expect(
      existsSync(join(root, 'lib/thesis-static-params.ts')),
      'lib/thesis-static-params.ts enumerated ids at build time and threw on a PostgREST blip, failing the whole Pages build'
    ).toBe(false);

    const enumerating = sourceFiles(join(root, 'app'))
      .filter((path) => /export\s+(async\s+)?function\s+generateStaticParams/.test(readFileSync(path, 'utf8')))
      .map((path) => relative(root, path));
    expect(enumerating, 'no route may pre-enumerate ids from the database').toEqual([]);
  });

  it('links to a thesis detail with the query form, never the path form', () => {
    const offenders = [join(root, 'app'), join(root, 'components'), join(root, 'lib')]
      .flatMap(sourceFiles)
      .filter((path) => !path.endsWith('thesis-route-canon.test.ts'))
      .filter((path) => /\/portfolio\/theses\/[$`{]/.test(readFileSync(path, 'utf8')))
      .map((path) => relative(root, path));
    expect(offenders, 'build a thesis href with thesisDetailHref() from lib/portfolio-url-state').toEqual([]);
  });

  it('keeps the theses route a single static page', () => {
    const routeDir = join(root, 'app/portfolio/theses');
    const children = readdirSync(routeDir).filter((name) => statSync(join(routeDir, name)).isDirectory());
    expect(children, 'the theses route takes its id from `?thesis=`, not a nested segment').toEqual([]);
    expect(existsSync(join(routeDir, 'page.tsx'))).toBe(true);
  });
});
