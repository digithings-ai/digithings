import { describe, expect, it } from 'vitest';
import { readdirSync, readFileSync } from 'node:fs';
import { join, relative } from 'node:path';

const root = join(__dirname, '..');
const read = (rel: string) => readFileSync(join(root, rel), 'utf8');

/** Every non-test component source, as repo-relative paths. */
function componentSources(): string[] {
  const out: string[] = [];
  const walk = (dir: string) => {
    for (const e of readdirSync(dir, { withFileTypes: true })) {
      const p = join(dir, e.name);
      if (e.isDirectory()) walk(p);
      else if (/\.tsx?$/.test(e.name) && !/\.test\.tsx?$/.test(e.name)) {
        out.push(relative(root, p));
      }
    }
  };
  walk(join(root, 'components'));
  return out;
}

/**
 * Time-series charts — must ride lightweight-charts (lib/CHARTS.md, #1420).
 *
 * DERIVED, not hard-coded (#1747). The list used to name three files by hand;
 * all three were the orphaned Performance tab's charts and were deleted, which
 * would have left a hard-coded empty array silently passing forever. Scanning
 * instead means the canon binds the *next* time-series chart the moment it
 * imports the engine. The standalone drawdown chart left in #1548 — the
 * workspace's drawdown view rode the shared <SyncedTearsheet/>.
 *
 * The set stays derived so new app-local time-series surfaces are covered
 * without maintaining a second hand-written inventory.
 */
const ALL_COMPONENTS = componentSources();
const MIGRATED = ALL_COMPONENTS.filter((rel) => read(rel).includes("from 'lightweight-charts'"));

/** Categorical/composition surfaces — sanctioned to stay on recharts. */
const RECHARTS_SANCTIONED = [
  'components/portfolio/sleeve-stacked-chart.tsx',
  'components/observability/AttributionTab.tsx',
  'components/observability/DecisionScorecardTab.tsx',
  'components/twelve-x/ConsensusTab.tsx',
];

describe('chart engine ruling (lib/CHARTS.md, #1420)', () => {
  // MIGRATED is derived and currently empty, so the two loops below have no
  // subjects. Assert the DERIVATION worked: without this, a broken walk (wrong
  // root, changed extension) would empty the set and every canon rule would
  // pass vacuously — the false green #1747 was careful not to ship.
  it('the component scan that derives the migrated set is live', () => {
    expect(ALL_COMPONENTS.length).toBeGreaterThan(20);
    expect(ALL_COMPONENTS).toContain('components/portfolio/AllocationsPositionsTable.tsx');
    // Sanity-check the predicate itself against a file known to import the
    // engine — the scaffold in lib/ (outside the scanned components/ tree).
    expect(read('lib/lw-chart.tsx')).toContain("from 'lightweight-charts'");
  });

  it('time-series charts import lightweight-charts and never recharts', () => {
    for (const rel of MIGRATED) {
      const src = read(rel);
      expect(src, `${rel} should draw with lightweight-charts`).toContain(
        "from 'lightweight-charts'"
      );
      expect(src, `${rel} should use the shared scaffold (lib/lw-chart)`).toContain(
        "from '@/lib/lw-chart'"
      );
      expect(src.includes("from 'recharts'"), `${rel} must not import recharts`).toBe(false);
    }
  });

  it('categorical/composition charts stay on recharts (no lightweight-charts creep)', () => {
    for (const rel of RECHARTS_SANCTIONED) {
      const src = read(rel);
      expect(src, `${rel} is a sanctioned recharts surface`).toContain("from 'recharts'");
      expect(
        src.includes("from 'lightweight-charts'") || src.includes("from '@/lib/lw-chart'"),
        `${rel} must not import lightweight-charts — it has no categorical grammar`
      ).toBe(false);
    }
  });

  it('components never call createChart directly — the scaffold owns the lifecycle', () => {
    for (const rel of MIGRATED) {
      const src = read(rel);
      expect(
        src.includes('createChart('),
        `${rel} should go through useLightweightChart, not createChart`
      ).toBe(false);
    }
  });

  it('CHARTS.md carries the engine ruling', () => {
    // Unwrap the markdown (blockquote prefixes + hard wraps) before matching.
    const doc = read('lib/CHARTS.md').replace(/\n>? ?/g, ' ');
    expect(doc).toContain('lightweight-charts is the canon for time-series');
    expect(doc).toContain('recharts is sanctioned for categorical/composition surfaces');
    expect(doc).toContain('lightweight-charts has no categorical grammar');
  });
});
