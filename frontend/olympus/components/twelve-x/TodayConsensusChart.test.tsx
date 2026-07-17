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
  it('renders the "Consensus" title', () => {
    const html = render(tenCurrencySeries());
    expect(html).toContain('Consensus');
  });

  it('renders the title as an uppercase eyebrow matching the sibling panels', () => {
    const html = render(tenCurrencySeries());
    // The frozen spec's `.section-eyebrow` is `text-transform: uppercase`; the
    // sibling Today headings ("Broker briefs", "Today's timeline") render the
    // eyebrow inline with `uppercase`. The "Consensus" heading MUST
    // match (sentence-case would diverge from the spec + neighbours).
    const heading = html.match(/<h2[^>]*>Consensus<\/h2>/);
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

  it('renders the bars (divergent track with markers)', () => {
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

  it('renders "Consensus" heading (not "Consensus average")', () => {
    const html = render(tenCurrencySeries());
    expect(html).toContain('Consensus');
    expect(html).not.toContain('Consensus average');
  });

  it('does NOT render the verbose subtitle explaining raw vs average', () => {
    const html = render(tenCurrencySeries());
    expect(html).not.toContain('raw latest scores');
    expect(html).not.toContain('Consensus tab');
  });

  it('passes exactly two markers (actual and prior) to ConsensusScoreBar', () => {
    const html = render(tenCurrencySeries());
    // The compact spec removes yesterday-average and 5-days-ago markers. Only
    // today's actual (white) and prior-run actual (for change) remain.
    // Note: 'prior' kind renders as 't-yday' class in ConsensusScoreBar.
    expect(html).toContain('t-actual');
    expect(html).toContain('t-yday');
    expect(html).not.toContain('t-ago');
  });

  it('renders the compact prior-run change without a visible label', () => {
    const html = render(tenCurrencySeries());
    expect(html).toMatch(/[+−-]\d\.\d{2}/);
    expect(html).not.toContain('vs prior');
  });

  it('does NOT render momentum-vs-average arrows or the "rate of change" legend', () => {
    const html = render(tenCurrencySeries());
    expect(html).not.toContain('▲');
    expect(html).not.toContain('▼');
    expect(html).not.toContain('rate of change');
    expect(html).not.toContain('actual vs average');
  });

  it('does NOT render yesterday or 5-days-ago legend keys', () => {
    const html = render(tenCurrencySeries());
    expect(html).not.toContain('Yesterday');
    expect(html).not.toContain('5 days ago');
  });

  it('renders a friendly empty state with no series (no crash)', () => {
    const html = render([]);
    expect(html).toContain('Consensus');
    expect(html.toLowerCase()).toContain('no consensus');
    expect(html).not.toContain('tc-row');
  });
});
