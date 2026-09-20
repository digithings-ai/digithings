import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { buildLevelFixSeries } from '@/lib/twelve-x/level-vs-fix';
import type { FxIdeaEvalRow, FxTradeIdeaRow } from '@/lib/twelve-x/types';
import LevelFixChart from './LevelFixChart';

const TRADE_LEVELS = {
  entry_low: { value: '1.0800', provenance: 'broker_quoted', source_ref: 'desk' },
  entry_high: { value: '1.0850', provenance: 'broker_quoted', source_ref: 'desk' },
  stop: { value: '1.0700', provenance: 'broker_quoted', source_ref: 'desk' },
  targets: [{ value: '1.1000', provenance: 'broker_quoted', source_ref: 'desk' }],
  risk_reward: 2,
  status: 'complete',
};

function idea(): FxTradeIdeaRow {
  return {
    run_date: '2026-06-12',
    rank: 1,
    pair: 'EUR/USD',
    direction: 'long',
    title: 'EUR/USD long',
    thesis: '',
    catalyst: '',
    levels: [],
    citations: [],
    as_of: '2026-06-26T00:00:00Z',
    trade_levels: TRADE_LEVELS,
  };
}

function evalRow(): FxIdeaEvalRow {
  return {
    run_date: '2026-06-12',
    rank: 1,
    horizon_days: 0,
    pair: 'EUR/USD',
    direction: 'long',
    status: 'resolved',
    entry_date: '2026-06-13',
    exit_date: '2026-06-18',
    entry_fix: 1.082,
    exit_fix: 1.095,
    ret: null,
    hold_return: 0.012,
    sigma_entry: null,
    hit: true,
    directional_win: true,
    significant_hit: false,
    n_sessions: 4,
    as_of: '2026-06-26T00:00:00Z',
  };
}

describe('LevelFixChart', () => {
  it('renders entry/stop/target captions with entry-exit markers', () => {
    const series = buildLevelFixSeries(
      idea(),
      evalRow(),
      [
        { date: '2026-06-13', fix: 1.082 },
        { date: '2026-06-14', fix: 1.086 },
      ],
    );
    const html = renderToStaticMarkup(createElement(LevelFixChart, { series }));
    expect(html).toContain('data-testid="level-fix-chart"');
    expect(html).toContain('EUR/USD fix vs published levels');
    expect(html).toContain('1.0800–1.0850');
    expect(html).toContain('1.0700');
    expect(html).toContain('1.1000');
    expect(html).toContain('In 1.0820');
    expect(html).toContain('Out 1.0950');
    expect(html).not.toContain('anchors only');
    // Kit reference overlays (Q3b slice 5a): entry band, stop + target
    // lines, and entry/exit anchor dots ride the shared primitive.
    expect(html).toContain('data-chart-layer="reference-band"');
    expect(html).toContain('ts-ref-band-accent');
    expect(html).toContain('data-chart-layer="reference-line"');
    expect(html).toContain('ts-ref-tone-warn');
    expect(html).toContain('data-chart-layer="reference-marker"');
    expect(html).toContain('<title>In 1.0820</title>');
    expect(html).toContain('<title>Out 1.0950</title>');
  });

  it('maps the published levels inside the plot rather than pinning them to its edges', () => {
    const series = buildLevelFixSeries(
      idea(),
      evalRow(),
      [
        { date: '2026-06-13', fix: 1.082 },
        { date: '2026-06-14', fix: 1.086 },
      ],
    );
    const html = renderToStaticMarkup(createElement(LevelFixChart, { series }));
    // The kit draws on a 1000x300 viewBox with a padded plot area. A level whose
    // value falls outside the frame's domain clamps flat to the plot edge, which
    // reads as "at the boundary" whatever the real price is. The component now
    // passes a domain covering the levels, so each line must sit strictly inside
    // the plot and the lower level (stop) must sit lower on screen than the
    // target. This is the assertion that fails under auto-domain.
    const ys = [...html.matchAll(/<line[^>]*y1="([\d.]+)"[^>]*data-chart-layer="reference-line"/g)].map(
      (m) => Number(m[1]),
    );
    expect(ys).toHaveLength(2);
    const PLOT_TOP = 30;
    const PLOT_BOTTOM = 286;
    for (const y of ys) {
      expect(y).toBeGreaterThan(PLOT_TOP);
      expect(y).toBeLessThan(PLOT_BOTTOM);
    }
    // Stop 1.0700 is below target 1.1000, so it maps to a larger y.
    expect(Math.max(...ys)).toBeGreaterThan(Math.min(...ys));
    expect(Math.max(...ys) - Math.min(...ys)).toBeGreaterThan(20);
  });

  it('badges the anchors-only fallback', () => {
    const series = buildLevelFixSeries(idea(), evalRow(), []);
    expect(series.anchorsOnly).toBe(true);
    const html = renderToStaticMarkup(createElement(LevelFixChart, { series }));
    expect(html).toContain('anchors only');
    expect(html).toContain('In 1.0820');
  });

  it('renders an empty state with no fixes and no levels', () => {
    const series = buildLevelFixSeries({ ...idea(), trade_levels: null }, null, []);
    const html = renderToStaticMarkup(createElement(LevelFixChart, { series }));
    expect(html).toContain('No fix data for EUR/USD yet.');
  });

  it('renders the series with no reference layers when no levels are published', () => {
    const series = buildLevelFixSeries({ ...idea(), trade_levels: null }, null, [
      { date: '2026-06-13', fix: 1.082 },
      { date: '2026-06-14', fix: 1.086 },
    ]);
    const html = renderToStaticMarkup(createElement(LevelFixChart, { series }));
    expect(html).toContain('<svg');
    expect(html).not.toContain('reference-band');
    expect(html).not.toContain('reference-line');
    expect(html).not.toContain('reference-marker');
  });
});
