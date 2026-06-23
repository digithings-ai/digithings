import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, it, expect, vi } from 'vitest';

// TodayActionsPanel renders next/link; render its children inline for a static test.
vi.mock('next/link', () => ({ default: (props: { children?: unknown }) => props.children }));

import { MoveHero } from './move-hero';

const navOk = {
  index: 104.2,
  dailyPct: 0.3,
  benchTicker: 'SPY',
  excessPct: 4.2,
  sinceDate: '2026-04-12',
};

describe('MoveHero', () => {
  it('leads with the move on an action day', () => {
    const html = renderToStaticMarkup(
      createElement(MoveHero, {
        regime: 'Risk-Off Consolidation',
        regimeLabel: 'neutral',
        asOf: '2026-06-20',
        runType: 'delta',
        actions: [{ ticker: 'NVDA', current_pct: 8, recommended_pct: 6, action: 'TRIM' }],
        nav: navOk,
      })
    );
    expect(html).toContain('Today'); // hero title
    expect(html).toContain('NVDA');
    expect(html).toContain('TRIM');
    expect(html).toContain('104.2'); // NAV index in the status line
    expect(html).toContain('SPY');
  });

  it('is never empty on a HOLD day', () => {
    const html = renderToStaticMarkup(
      createElement(MoveHero, {
        regime: 'Broadening Rally',
        regimeLabel: 'bullish',
        asOf: '2026-06-21',
        runType: 'delta',
        actions: [{ ticker: 'SPY', current_pct: 50, recommended_pct: 50, action: 'HOLD' }],
        nav: navOk,
      })
    );
    expect(html).toContain('No changes proposed'); // from TodayActionsPanel
    expect(html).toContain('104.2');
  });

  it('shows the regime name', () => {
    const html = renderToStaticMarkup(
      createElement(MoveHero, {
        regime: 'Risk-Off Consolidation',
        regimeLabel: 'neutral',
        asOf: '2026-06-20',
        runType: null,
        actions: [],
        nav: navOk,
      })
    );
    expect(html).toContain('Risk-Off Consolidation');
  });
});
