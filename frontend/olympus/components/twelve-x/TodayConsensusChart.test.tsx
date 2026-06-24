import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { G10_CURRENCIES } from '@/lib/twelve-x/types';
import type { FxConsensusSnapshotRow } from '@/lib/twelve-x/types';
import { TodayConsensusChart } from './TodayConsensusChart';

/**
 * Build a 6-run ascending consensus series for every G10 currency so each
 * currency has enough history for the trailing-5 average, yesterday's average
 * and the ~5-days-ago average to all be derivable (non-null markers).
 */
function tenCurrencySeries(): FxConsensusSnapshotRow[] {
  const dates = [
    '2026-06-17',
    '2026-06-18',
    '2026-06-19',
    '2026-06-20',
    '2026-06-21',
    '2026-06-22',
  ];
  const rows: FxConsensusSnapshotRow[] = [];
  G10_CURRENCIES.forEach((currency, ci) => {
    dates.forEach((run_date, di) => {
      // Deterministic, varied scores in [-2, 2]; sign alternates per currency.
      const score = (ci % 2 === 0 ? 1 : -1) * (0.3 + di * 0.2);
      rows.push({
        run_date,
        currency,
        timeframe: 'medium',
        horizon_weeks: null,
        weighted: true,
        score,
        confidence: 0.7,
        agreement: 0.6,
        tilt: 0.1,
        n_eff: 5,
        n_brokers: 5,
        n_views: 8,
        bullish_pct: 0.5,
        bearish_pct: 0.3,
        neutral_pct: 0.1,
        watch_pct: 0.1,
        as_of: `${run_date}T12:00:00Z`,
      });
    });
  });
  return rows;
}

function render(series: FxConsensusSnapshotRow[]): string {
  return renderToStaticMarkup(createElement(TodayConsensusChart, { series }));
}

describe('TodayConsensusChart', () => {
  it('renders the "Consensus average" title', () => {
    const html = render(tenCurrencySeries());
    expect(html).toContain('Consensus average');
  });

  it('renders one row per G10 currency for a 10-currency series', () => {
    const html = render(tenCurrencySeries());
    for (const ccy of G10_CURRENCIES) {
      expect(html).toContain(`>${ccy}<`);
    }
    // "tc-row " (trailing space) is the per-currency row wrapper class; the
    // grid container is "tc-rows" so it is excluded. Expect exactly G10 rows.
    const rowCount = (html.match(/class="tc-row /g) ?? []).length;
    expect(rowCount).toBe(G10_CURRENCIES.length);
  });

  it('shows all five legend keys', () => {
    const html = render(tenCurrencySeries());
    // renderToStaticMarkup escapes apostrophes to &#x27;, so match on the
    // unambiguous, apostrophe-free portions of each legend label.
    expect(html).toContain('Consensus average (bar');
    expect(html).toContain('actual'); // Today's actual
    expect(html).toContain('Yesterday'); // Yesterday's avg
    expect(html).toContain('5 days ago avg');
    expect(html).toContain('actual vs average');
  });

  it('renders the Proposed view by default (bars present, not the movers cards)', () => {
    const html = render(tenCurrencySeries());
    // Proposed bars render the divergent track + legend-coded marker ticks.
    expect(html).toContain('dbar-track');
    expect(html).toContain('dbar-tick');
    // Proposed is pressed; Current is not the active view.
    expect(html).toContain('aria-pressed="true"');
    // The plain movers cards (Current view) must not be the rendered content.
    expect(html).not.toContain('oc-score');
  });

  it('renders markers (actual / yesterday / ago ticks) in the markup', () => {
    const html = render(tenCurrencySeries());
    expect(html).toContain('t-actual');
    expect(html).toContain('t-yday');
    expect(html).toContain('t-ago');
  });

  it('renders a friendly empty state with no series (no crash)', () => {
    const html = render([]);
    expect(html).toContain('Consensus average');
    expect(html.toLowerCase()).toContain('no consensus');
    expect(html).not.toContain('tc-row');
  });
});
