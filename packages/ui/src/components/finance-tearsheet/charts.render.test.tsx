import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { ContributionReturnChart, MultiTimeSeries, SignedBars, TimeSeries } from './charts';

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

describe('Chart references (Q3b slice 5a, #4443)', () => {
  const points = [
    { t: '2026-06-01', v: 1.0 },
    { t: '2026-06-02', v: 1.2 },
    { t: '2026-06-03', v: 0.9 },
  ];

  it('TimeSeries renders bands beneath, dashed lines, and date-snapped markers', () => {
    const html = renderToStaticMarkup(createElement(TimeSeries, {
      points,
      ariaLabel: 'Fix vs levels',
      references: {
        bands: [{ from: 1.0, to: 1.1 }],
        lines: [{ value: 0.8, tone: 'warn' }, { value: 1.3, tone: 'accent', dashed: false }],
        markers: [{ t: '2026-06-02', v: 1.2, label: 'In 1.2000' }],
      },
    }));

    expect(html).toContain('data-chart-layer="reference-band"');
    expect(html).toContain('data-chart-layer="reference-line"');
    expect(html).toContain('data-chart-layer="reference-marker"');
    expect(html).toContain('ts-ref-band-accent');
    expect(html).toContain('ts-ref-tone-warn');
    expect(html).toContain('ts-ref-dashed');
    expect(html).toContain('<title>In 1.2000</title>');
    // The band sits beneath the series: its layer precedes the series path.
    expect(html.indexOf('reference-band')).toBeLessThan(html.indexOf('ts-line ts-tone'));
    // The solid line opts out of the default dash.
    expect(html.match(/ts-ref-dashed/g)).toHaveLength(1);
  });

  it('omits every reference layer when no references are given (backward compatible)', () => {
    const html = renderToStaticMarkup(createElement(TimeSeries, {
      points,
      ariaLabel: 'Plain series',
    }));

    expect(html).not.toContain('reference-band');
    expect(html).not.toContain('reference-line');
    expect(html).not.toContain('reference-marker');
    expect(html).not.toContain('ts-ref-');
  });

  it('clamps out-of-domain lines to the plot and snaps markers to the nearest date', () => {
    const html = renderToStaticMarkup(createElement(TimeSeries, {
      points,
      domain: [0, 2],
      ariaLabel: 'Clamped refs',
      references: {
        lines: [{ value: 99, label: 'Far away' }],
        markers: [{ t: '2026-06-10', v: 1.0 }],
      },
    }));

    expect(html).toContain('data-chart-layer="reference-line"');
    expect(html).toContain('<title>Far away</title>');
    // The clamped line pins to a plot edge: y1 and y2 are equal (horizontal).
    expect(html).toMatch(/y1="([\d.]+)" x2="[\d.]+" y2="\1"/);
    // The marker snaps to the last plotted date instead of vanishing.
    expect(html).toContain('data-chart-layer="reference-marker"');
  });

  it('MultiTimeSeries honors explicit domain, per-series color, and references', () => {
    const html = renderToStaticMarkup(createElement(MultiTimeSeries, {
      series: [
        { id: 'AAA', label: 'AAA', points, color: 'var(--accent)' },
        { id: 'BBB', label: 'BBB', points, dashed: true, tone: 'mute' },
      ],
      domain: [-2, 2],
      references: {
        bands: [{ from: 1.25, to: 2, tone: 'up' }],
        lines: [{ value: 0 }],
      },
      ariaLabel: 'Consensus over time',
    }));

    expect(html).toContain('data-series="AAA"');
    expect(html).toContain('stroke:var(--accent)');
    expect(html).toContain('ts-line-dashed');
    expect(html).toContain('ts-ref-band-up');
    expect(html).toContain('data-chart-layer="reference-line"');
  });
});
