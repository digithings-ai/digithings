import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { ContributionReturnChart, SignedBars } from './charts';

describe('ContributionReturnChart', () => {
  it('renders signed contribution segments and portfolio return in one SVG', () => {
    const html = renderToStaticMarkup(createElement(ContributionReturnChart, {
      points: [
        { t: '2026-07-01', returnPct: 0, contributions: { AAA: 0, HEDGE: 0 } },
        { t: '2026-07-02', returnPct: 1.5, contributions: { AAA: 2, HEDGE: -0.5 } },
      ],
      colors: { AAA: 'var(--accent)', HEDGE: 'var(--down)' },
      benchmark: { label: 'SPY', values: [0, 1.1] },
    }));

    expect(html).toContain('data-chart-layer="contributions"');
    expect(html).toContain('data-series="AAA"');
    expect(html).toContain('data-series="HEDGE"');
    expect(html).toContain('data-chart-layer="portfolio-return"');
    expect(html).toContain('data-chart-layer="benchmark-return"');
    expect(html).toContain('data-series="SPY"');
    expect(html).toContain('ts-contribution-axis');
    expect(html.match(/2026-07-01/g)).toHaveLength(1);
    expect(html.match(/2026-07-02/g)).toHaveLength(1);
    expect(html).toContain('ts-grid-zero');
    expect(html.match(/<svg/g)).toHaveLength(1);
  });
});
describe('SignedBars labels (Q3b slice 4, #4443)', () => {
  it('renders one angled tick label per provided label, parallel to values', () => {
    const html = renderToStaticMarkup(createElement(SignedBars, {
      values: [2.5, -1.25, 0.75],
      labels: ['AAA', 'BBB', 'CCC'],
      fmt: (v: number) => `${v.toFixed(2)}%`,
      ariaLabel: 'Contribution by holding',
    }));

    expect(html).toContain('>AAA</text>');
    expect(html).toContain('>BBB</text>');
    expect(html).toContain('>CCC</text>');
    expect(html).toContain('rotate(-30');
    // Label gutter: anchors sit 28px above the viewBox bottom so the -30°
    // labels land inside the plot gutter instead of clipping (default
    // height 220 → y=192; the first cut anchored at height-10).
    expect(html).toContain('y="192"');
    expect(html).toContain('<title>AAA: 2.50%</title>');
    expect(html).toContain('<title>BBB: -1.25%</title>');
    expect(html).toContain('ts-tone-up');
    expect(html).toContain('ts-tone-down');
  });

  it('leaves bars unlabeled when no labels are given (backward compatible)', () => {
    const html = renderToStaticMarkup(createElement(SignedBars, {
      values: [1, -2],
      ariaLabel: 'Signed bars',
    }));

    expect(html).not.toContain('rotate(-30');
    expect(html).toContain('<title>');
  });

  it('ignores labels beyond the values and blanks within them', () => {
    const html = renderToStaticMarkup(createElement(SignedBars, {
      values: [1, -2],
      labels: ['AAA', '', 'EXTRA'],
      ariaLabel: 'Signed bars',
    }));

    expect(html).toContain('>AAA</text>');
    expect(html).not.toContain('>EXTRA</text>');
    expect(html).toContain('<title>AAA:');
  });

  it('renders the honest empty when there is nothing to plot', () => {
    const html = renderToStaticMarkup(createElement(SignedBars, {
      values: [],
      ariaLabel: 'Signed bars',
    }));

    expect(html).toContain('no trades');
    expect(html).not.toContain('<rect');
  });
});
