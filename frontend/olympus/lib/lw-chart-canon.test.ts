import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const root = join(__dirname, '..');
const read = (rel: string) => readFileSync(join(root, rel), 'utf8');

/** Time-series charts — must ride lightweight-charts (lib/CHARTS.md, #1420).
 * The standalone drawdown chart is gone (#1548): the workspace's drawdown
 * view rides the shared <SyncedTearsheet/> from @digithings/web. */
const MIGRATED = [
  'components/portfolio/performance-chart-workspace.tsx',
  'components/portfolio/performance-rolling-chart.tsx',
  'components/portfolio/PositionDrilldown.tsx',
];

/** Categorical/composition surfaces — sanctioned to stay on recharts. */
const RECHARTS_SANCTIONED = [
  'components/portfolio/sleeve-stacked-chart.tsx',
  'components/observability/AttributionTab.tsx',
  'components/observability/DecisionScorecardTab.tsx',
  'components/twelve-x/ConsensusTab.tsx',
];

describe('chart engine ruling (lib/CHARTS.md, #1420)', () => {
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
