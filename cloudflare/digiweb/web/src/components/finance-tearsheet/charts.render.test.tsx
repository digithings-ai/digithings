import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { ContributionReturnChart } from './charts';

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