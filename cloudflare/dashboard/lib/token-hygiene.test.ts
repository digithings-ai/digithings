import { describe, it, expect } from 'vitest';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';

function walk(dir: string, out: string[] = []): string[] {
  for (const e of readdirSync(dir)) {
    const p = join(dir, e);
    if (e === 'node_modules' || e === '.next') continue;
    if (statSync(p).isDirectory()) walk(p, out);
    else if (/\.(tsx?|css)$/.test(e)) out.push(p);
  }
  return out;
}

describe('canon token hygiene (#1402)', () => {
  const files = walk(join(__dirname, '..', 'components'));
  it('no pre-canon vocabulary survives in components (text-text-*, bg-bg-*, fin-*)', () => {
    // The digiweb canon bridge (@digithings/web web-theme.css) owns the utility
    // vocabulary: text-ink/-soft/-mute, bg-bg/surface/term-bg, border-hair,
    // text-up/down/warn/accent. The dashboard-local @theme block that used to
    // define these names is gone — any survivor would silently compile to
    // nothing under Tailwind v4.
    const legacy =
      /text-text-|bg-bg-(?:primary|secondary|glass)|border-border-|fin-blue|fin-green|fin-red|fin-amber|fin-purple/;
    const offenders = files
      // *.test.* keep intentional negative guards like not.toContain('fin-purple')
      .filter((f) => !/\.test\.tsx?$/.test(f))
      .filter((f) => legacy.test(readFileSync(f, 'utf8')));
    expect(offenders).toEqual([]);
  });
  it('no #a78bfa or raw rgba(59,130,246) literal survives in components', () => {
    // The Phase-0 PHASE_DEFERRED exemptions (workspace + price/contribution
    // charts + DeltaDaySummary) are gone: every chart now draws from
    // lib/chart-colors.ts (#1402), the single sanctioned color source.
    const offenders = files.filter((f) => {
      const s = readFileSync(f, 'utf8');
      return s.includes('#a78bfa') || s.includes('rgba(59,130,246') || s.includes('rgba(59, 130, 246');
    });
    expect(offenders).toEqual([]);
  });

  it('dashboard core has no glass-card class (tonal slabs are .oly-slab)', () => {
    const appFiles = walk(join(__dirname, '..', 'app'));
    const core = [...files, ...appFiles].filter((f) => !/\.test\.tsx?$/.test(f));
    const offenders = core.filter((f) => {
      const stripped = readFileSync(f, 'utf8')
        .replace(/\/\*[\s\S]*?\*\//g, '')
        .replace(/\{\/\*[\s\S]*?\*\/\}/g, '')
        .replace(/\/\/.*$/gm, '');
      return /\bglass-card\b/.test(stripped);
    });
    expect(offenders).toEqual([]);
  });

  it('dashboard chrome has no rounded-sm/md/lg/xl (true circles may keep rounded-full)', () => {
    const chrome = /\brounded-(?:sm|md|lg|xl|2xl|3xl|4xl)\b/;
    const offenders = files
      .filter((f) => !/\.test\.tsx?$/.test(f))
      .filter((f) => chrome.test(readFileSync(f, 'utf8')));
    expect(offenders).toEqual([]);
  });
});
