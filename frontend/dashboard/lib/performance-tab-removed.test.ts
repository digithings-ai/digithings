import { describe, expect, it } from 'vitest';
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { join, relative } from 'node:path';

/**
 * Revival guard for the deleted Performance-tab subtree (#1747, #1761).
 *
 * `components/portfolio/tabs/PerformanceTab.tsx` was orphaned on 2026-07-19 by
 * b15025ce ("redesign portfolio experience", #1607) and stayed on disk, dead,
 * for six weeks. `PortfolioTabId` is `'holdings' | 'theses'`, so `?tab=performance`
 * renders Holdings (see portfolio-url-state.test.ts); the live Performance
 * screen is `app/portfolio/performance/page.tsx`, which renders
 * `PerformanceTearsheetView` over persisted `portfolio_metrics` and, per its own
 * docstring, "does not recalculate headline metrics from raw NAV".
 *
 * This test exists because the subtree carried two confirmed WRONG-NUMBER bugs
 * that were only invisible, not fixed. Restoring any of these files without
 * fixing them re-ships both:
 *
 *   1. #1747 — false server provenance. `portfolio-risk-metrics.ts:86-95`
 *      `computeEffectivePortfolioRiskMetrics` did
 *      `serverMetrics?.sharpe ?? navMetrics?.sharpe ?? null`, which conflates
 *      "the server deliberately SUPPRESSED this value" with "the server has no
 *      value". The writer NULLs sharpe/volatility/max_drawdown below
 *      `_MIN_HISTORY_ROWS = 20` and marks the row
 *      `computed_from='refresh_script_insufficient_history'` precisely so the UI
 *      can say "insufficient history" — but `computed_from` is dropped in the
 *      `queries.ts` mapping and absent from `ServerPortfolioMetrics`, so the
 *      client cannot see the suppression. Result: Sharpe -5.71 / ann. vol 4.14%
 *      recomputed from 15 sparse NAV rows and captioned with the server's
 *      `generated_at`. A revival must propagate the suppression signal, not
 *      re-add the `??` chain.
 *
 *   2. #1761 — `advanced-stats-panel.tsx:85` `annFactor = 252 / returns.length`,
 *      conflating "number of NAV observations" with "elapsed trading days":
 *      14 returns over 27 NYSE trading days gave 18.0 instead of 9.33, and
 *      "Annualized Return -21.10%" for a book down 1.31%. Do NOT simply fix the
 *      divisor. `nav_history` is a CALENDAR-day series by design (2026-07-18 Sat
 *      and 07-19 Sun are both present), so `252/N` is unit-wrong in both
 *      regimes — gappy over-annualizes, dense-as-designed under-annualizes
 *      (252/38 = 6.63). A revival should SUPPRESS the annualized figure below a
 *      minimum history length rather than rescale it.
 *
 * So: if you are deliberately reviving this surface, fix both bugs, then delete
 * this file in the same commit.
 */
const REMOVED = [
  'components/portfolio/tabs/PerformanceTab.tsx',
  'components/portfolio/PositionDrilldown.tsx',
  'components/portfolio/advanced-stats-panel.tsx',
  'components/portfolio/performance-chart-workspace.tsx',
  'components/portfolio/performance-date-range.tsx',
  'components/portfolio/performance-rolling-chart.tsx',
  'components/portfolio/position-pnl-table.tsx',
  'lib/performance-series.ts',
  'lib/portfolio-risk-metrics.ts',
  'lib/position-drilldown.ts',
  'lib/position-first-entry.ts',
];

const root = join(__dirname, '..');

/** Every non-test source file in the app, as repo-relative paths. */
function sources(): string[] {
  const out: string[] = [];
  const walk = (dir: string) => {
    for (const e of readdirSync(dir, { withFileTypes: true })) {
      if (e.name === 'node_modules' || e.name === '.next' || e.name.startsWith('.')) continue;
      const p = join(dir, e.name);
      if (e.isDirectory()) walk(p);
      else if (/\.tsx?$/.test(e.name)) out.push(relative(root, p));
    }
  };
  for (const d of ['app', 'components', 'lib']) walk(join(root, d));
  return out;
}

describe('orphaned Performance tab stays deleted (#1747, #1761)', () => {
  it('none of the subtree files are back on disk', () => {
    const present = REMOVED.filter((rel) => existsSync(join(root, rel)));
    expect(
      present,
      `Restored without fixing the two confirmed wrong-number bugs? Read this ` +
        `file's header before re-adding: the ?? server-provenance conflation ` +
        `(#1747) and annFactor = 252/returns.length (#1761).`
    ).toEqual([]);
  });

  it('no source file imports the deleted modules', () => {
    // Module specifiers, so a same-named module elsewhere is not a false hit.
    const specifiers = REMOVED.map((rel) => rel.replace(/\.tsx?$/, ''));
    const offenders: string[] = [];
    for (const rel of sources()) {
      if (rel === relative(root, __filename)) continue;
      const src = readFileSync(join(root, rel), 'utf8');
      for (const spec of specifiers) {
        // '@/lib/portfolio-risk-metrics' or a relative './portfolio-risk-metrics'
        const bare = spec.split('/').pop()!;
        if (new RegExp(`from\\s*['"](?:@/${spec}|[./]+(?:[\\w-]+/)*${bare})['"]`).test(src)) {
          offenders.push(`${rel} → ${spec}`);
        }
      }
    }
    expect(offenders, 'dangling imports into the deleted Performance subtree').toEqual([]);
  });

  it('?tab=performance still resolves to a live surface, not the deleted tab', () => {
    // The legacy query param must keep redirecting to the real route, and that
    // route must not depend on anything this PR deleted.
    const urlState = readFileSync(join(root, 'lib/portfolio-url-state.ts'), 'utf8');
    expect(urlState).toContain("href: '/portfolio/performance'");
    expect(existsSync(join(root, 'app/portfolio/performance/page.tsx'))).toBe(true);
    const page = readFileSync(join(root, 'app/portfolio/performance/page.tsx'), 'utf8');
    expect(page).toContain('PerformanceTearsheetView');
  });
});
