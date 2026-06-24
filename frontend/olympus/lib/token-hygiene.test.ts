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

// The recharts/wash fills below carry the SAME rgba(59,130,246) literal but are
// owned by later phases (Phase-3 Performance + Phase-2 Documents). Phase 0 purges
// only the Holdings table bar + the drilldown line; the guard is widened to these
// files when those phases land. Until then they are deliberately exempted so an
// untouched surface does not fail this gate. (Plan note, Task 12.)
const PHASE_DEFERRED = [
  'DeltaDaySummary.tsx',
  'performance-chart-workspace.tsx',
  'PositionPriceChart.tsx',
  'PositionContributionChart.tsx',
];

describe('F5 token hygiene', () => {
  const files = walk(join(__dirname, '..', 'components'));
  it('no text-fin-purple literal survives in components', () => {
    const offenders = files.filter((f) => readFileSync(f, 'utf8').includes('text-fin-purple'));
    expect(offenders).toEqual([]);
  });
  it('no #a78bfa or raw rgba(59,130,246) literal survives in components (Phase-0 scope)', () => {
    const offenders = files
      .filter((f) => !PHASE_DEFERRED.some((d) => f.endsWith(d)))
      .filter((f) => {
        const s = readFileSync(f, 'utf8');
        return s.includes('#a78bfa') || s.includes('rgba(59,130,246') || s.includes('rgba(59, 130, 246');
      });
    expect(offenders).toEqual([]);
  });
});
