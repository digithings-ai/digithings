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

  it('renders the title as an uppercase eyebrow matching the sibling panels', () => {
    const html = render(tenCurrencySeries());
    // The frozen spec's `.section-eyebrow` is `text-transform: uppercase`; the
    // sibling Today headings ("Broker briefs", "Today's timeline") render the
    // eyebrow inline with `uppercase`. The "Consensus average" heading MUST
    // match (sentence-case would diverge from the spec + neighbours).
    const heading = html.match(/<h2[^>]*>Consensus average<\/h2>/);
    expect(heading).not.toBeNull();
    expect(heading?.[0]).toContain('uppercase');
    // The `.section-eyebrow`/`.soft` tokens are NOT defined in globals.css
    // (spec-only) — they must not be carried as dead classes here.
    expect(heading?.[0]).not.toContain('section-eyebrow');
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

  it('renders the bars (divergent track + legend-coded marker ticks)', () => {
    const html = render(tenCurrencySeries());
    expect(html).toContain('dbar-track');
    expect(html).toContain('dbar-tick');
  });

  it('has no Proposed/Current toggle (bars are the only view)', () => {
    const html = render(tenCurrencySeries());
    // The "Proposed | Current" toggle was leftover demo language and is gone:
    // no toggle buttons, no view discriminator, no Current movers branch.
    expect(html).not.toContain('aria-pressed');
    expect(html).not.toContain('data-view="proposed"');
    expect(html).not.toContain('data-view="current"');
    expect(html).not.toContain('>Proposed<');
    expect(html).not.toContain('>Current<');
    // The Current movers cards lived in the only `overflow-x-auto` scroller in
    // this component; with that branch deleted the scroller is gone too.
    expect(html).not.toContain('overflow-x-auto');
  });

  it('labels the chart as the trailing 5-run average (subtitle + per-row "avg" cue)', () => {
    const html = render(tenCurrencySeries());
    // Subtitle disambiguates Today (5-run average) from the Consensus tab (raw
    // latest score) — the two intentionally differ, so this must be explicit.
    expect(html).toContain('Trailing 5-run average');
    expect(html).toContain('Consensus tab');
    // The headline value column carries a small "avg" unit cue so the number
    // reads as e.g. "+0.90 avg" — the cue is a nested span right after the
    // signed 2-dp value.
    expect(html).toContain('avg');
    expect(html).toMatch(/[+−-]?\d\.\d{2}<span[^>]*>avg<\/span>/);
  });

  it('renders momentum direction (▲ green for a bull ccy, ▼ red for a bear ccy)', () => {
    const html = render(tenCurrencySeries());
    // The fixture's even-indexed currencies (USD, ci=0) ascend to a positive
    // actual above their trailing average → momentum +0.40 (▲, fin-green).
    // Odd-indexed (EUR, ci=1) descend → momentum -0.40 (▼, fin-red). This pins
    // the actual-vs-average rate-of-change semantics + arrow direction + sign.
    // The momentum cell is the only span carrying the "rate of change" title.
    expect(html).toMatch(
      /class="[^"]*text-fin-green"[^>]*rate of change[^>]*>▲ \+0\.40<\/span>/,
    );
    expect(html).toMatch(
      /class="[^"]*text-fin-red"[^>]*rate of change[^>]*>▼ -0\.40<\/span>/,
    );
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
