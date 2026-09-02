/**
 * Test-only fixture for a `daily_snapshots` row + the parsed
 * {@link SnapshotEnvelope} digest payload. Mirrors the shape Pydantic emits
 * (`digiquant.atlas.snapshot.SnapshotEnvelope.model_dump()`).
 *
 * Kept under `__fixtures__/` so the production bundle never imports it.
 */
import type { DigestPayload, SnapshotEnvelope } from '../snapshot-types';

export type SnapshotRowFixture = {
  date: string;
  run_type: string | null;
  baseline_date: string | null;
  snapshot: unknown;
  created_at: string | null;
};

/** Mutable copy of a DigestPayload — useful when tests want to tweak fields. */
export function fixtureDigest(): DigestPayload {
  return {
    segment: 'master',
    date: '2026-04-27',
    bias: 'bullish',
    headline: 'Tech rally extends as macro stress eases',
    material_findings: [
      {
        label: 'NVDA breaks resistance',
        summary: 'Closes above 1,200 on heavy volume.',
        source_ids: ['src-1'],
      },
    ],
    sources: [
      { id: 'src-1', title: 'Bloomberg market wrap', url: 'https://example.com/src-1' },
    ],
    notes: 'Watch sentiment shifts at the open.',
    market_regime_snapshot:
      'Risk-on regime confirmed; VIX down 4% week-over-week, breadth healthy across cyclicals.',
    alt_data_dashboard:
      'Aggregate credit-card spending data turning higher; cargo throughput stable WoW.',
    institutional_summary:
      'Hedge funds increased net long exposure to mega-cap tech for the third consecutive week.',
    asset_classes_summary:
      'Treasuries flat; commodities mixed (gold +0.6%, WTI -1.2%); FX shows dollar weakness.',
    us_equities_summary:
      'S&P 500 +0.8%, NDX +1.4%, RUT +0.3%. Semis lead, energy lags.',
    thesis_tracker:
      'AI-Compute thesis remains intact; semis breadth confirms.',
    portfolio_recommendations:
      'Hold positioning; consider tactical add to NVDA on intraday weakness.',
    actionable_summary: [
      {
        priority: 1,
        label: 'Trim energy underweight',
        rationale: 'Crude inventories suggest mean reversion risk.',
      },
      {
        priority: 2,
        label: 'Monitor 10Y yields',
        rationale: 'A break above 4.6% would invalidate duration overweight.',
      },
    ],
    risk_radar: [
      {
        horizon_hours: 24,
        label: 'CPI release Tuesday',
        trigger: 'Hotter-than-expected core CPI > 0.4% MoM.',
      },
    ],
    segment_freshness: {
      master: { source: 'today', as_of: '2026-04-27' },
    },
  };
}

export function fixtureEnvelope(): SnapshotEnvelope {
  return {
    schema_version: 1,
    run_date: '2026-04-27',
    run_type: 'delta',
    baseline_date: '2026-04-26',
    published_at: '2026-04-27T11:30:00Z',
    digest: fixtureDigest(),
  };
}

export function fixtureSnapshotRow(): SnapshotRowFixture {
  return {
    date: '2026-04-27',
    run_type: 'delta',
    baseline_date: '2026-04-26',
    snapshot: fixtureDigest(),
    created_at: '2026-04-27T11:30:00Z',
  };
}
