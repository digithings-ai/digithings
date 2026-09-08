import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, it, expect, vi } from 'vitest';

// TodayActionsPanel renders next/link; render its children inline for a static test.
vi.mock('next/link', () => ({ default: (props: { children?: unknown }) => props.children }));

import { MoveHero } from './move-hero';

const navOk = {
  sincePct: -0.7,
  sinceDate: '2026-07-17',
  dailyPct: -0.7,
  benchTicker: 'SPY',
  excessPct: 4.2,
};

describe('MoveHero', () => {
  it('leads with the regime headline and shows the demoted move + honest percentages', () => {
    const html = renderToStaticMarkup(
      createElement(MoveHero, {
        regime: 'Risk-Off Consolidation',
        regimeLabel: 'caution',
        headline: 'Mixed signals persist as tech leads equities and USD strengthens.',
        confidence: 0.7,
        asOf: '2026-07-20',
        runType: 'delta',
        actions: [{ ticker: 'NVDA', current_pct: 8, recommended_pct: 6, action: 'TRIM' }],
        nav: navOk,
      })
    );
    expect(html).toContain('Mixed signals persist'); // headline is the marquee
    expect(html).toContain('Risk-Off Consolidation');
    expect(html).toContain('0.7'); // confidence chip
    expect(html).not.toContain('98.6'); // NAV index is never surfaced
    expect(html).toContain('since inception'); // honest since-inception clause
    expect(html).toContain('text-down">-0.7%</span><span class="text-ink-soft"> since inception');
    expect(html).toContain('1 change today'); // demoted move status (1 non-HOLD action)
    expect(html).toContain('data-brief-section="command"');
    expect(html).not.toContain('glass-card');
  });

  it('shows a HOLD-day move status as holding the book', () => {
    const html = renderToStaticMarkup(
      createElement(MoveHero, {
        regime: 'Broadening Rally',
        regimeLabel: 'bullish',
        headline: 'Breadth improves; defensives lag.',
        confidence: 0.8,
        asOf: '2026-07-21',
        runType: 'delta',
        actions: [{ ticker: 'SPY', current_pct: 50, recommended_pct: 50, action: 'HOLD' }],
        nav: navOk,
      })
    );
    expect(html).toContain('No rebalance today — holding the book');
  });

  it('omits the daily-delta clause when there is only one performance point', () => {
    const html = renderToStaticMarkup(
      createElement(MoveHero, {
        regime: 'Risk-Off Consolidation',
        regimeLabel: 'caution',
        headline: 'Quiet tape.',
        confidence: null,
        asOf: '2026-07-17',
        runType: null,
        actions: [],
        nav: { sincePct: -0.7, sinceDate: '2026-07-17', dailyPct: null, benchTicker: null, excessPct: null },
      })
    );
    expect(html).toContain('since inception');
    // No daily-delta clause (the " today" suffix on a signed pct) with one performance point.
    // ("No rebalance today" move-status copy is a separate string and may appear.)
    expect(html).not.toContain(' today<'); // daily-delta clause renders "<pct> today" in its own span
  });

  it('labels the daily delta with its own date when the book lags the digest (#1555)', () => {
    const html = renderToStaticMarkup(
      createElement(MoveHero, {
        regime: 'Risk-Off Consolidation',
        regimeLabel: 'caution',
        headline: 'Quiet tape.',
        confidence: null,
        asOf: '2026-08-03',
        runType: null,
        actions: [],
        nav: { sincePct: -0.6, sinceDate: '2026-07-17', dailyPct: -0.2, benchTicker: null, excessPct: null, asOfDate: '2026-07-31' },
      })
    );
    expect(html).toContain('on Jul 31');
    expect(html).not.toContain(' today<');
  });
});
