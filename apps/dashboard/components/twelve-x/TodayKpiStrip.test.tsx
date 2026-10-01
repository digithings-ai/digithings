import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import type { TodayKpis } from '@/lib/twelve-x/kpis';
import TodayKpiStrip from './TodayKpiStrip';

const EMPTY: TodayKpis = {
  runDate: null,
  ideaCount: 0,
  disputedCount: 0,
  briefCount: 0,
  brokerCount: null,
  hit: null,
  nextHighImpact: null,
};

const render = (kpis: TodayKpis) => renderToStaticMarkup(createElement(TodayKpiStrip, { kpis }));

describe('TodayKpiStrip', () => {
  it('keeps all six tiles and degrades missing values to an em dash', () => {
    const html = render(EMPTY);
    expect(html.match(/data-slot="stat"/g)).toHaveLength(6);
    // Run, brokers, hit rate, next release have no value; zero counts still read as 0.
    expect(html.match(/data-slot="stat-value"[^>]*>—</g)).toHaveLength(4);
    expect(html).toContain('no resolved ideas');
    expect(html).toContain('none scheduled in feed');
    expect(html).not.toContain('data-slot="stat-delta"');
    expect(html).not.toContain('data-slot="stat-spark"');
  });

  it('shows disputed ideas as a warn delta on the ideas tile', () => {
    const html = render({ ...EMPTY, runDate: '2026-06-22', ideaCount: 4, disputedCount: 2 });
    expect(html).toMatch(/data-slot="stat-delta" class="[^"]*text-warn[^"]*">2 disputed</);
  });

  it('draws the hit-rate interval on a 0–100% track', () => {
    const html = render({
      ...EMPTY,
      hit: { k: 6, n: 10, rate: 0.6, low: 0.31, high: 0.83 },
    });
    expect(html).toContain('>60%<');
    expect(html).toContain('n=10, 31%–83%');
    expect(html).toContain('data-slot="stat-spark"');
    expect(html).toContain('Hit-rate 95% interval');
  });
});
