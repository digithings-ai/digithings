import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { PortfolioContributionChart } from './PortfolioPerformanceCharts';
import type { ContributionReturnPoint } from '@digithings/ui';

const points: ContributionReturnPoint[] = [
  { t: '2026-08-24', returnPct: 0, contributions: { AAA: 0 } },
  { t: '2026-08-25', returnPct: 0.4, contributions: { AAA: 0 } },
  { t: '2026-08-26', returnPct: 0.8, contributions: { AAA: 1.2 } },
];

const render = (startsOn?: string | null) =>
  renderToStaticMarkup(
    createElement(PortfolioContributionChart, { points, benchmark: null, startsOn })
  );

describe('PortfolioContributionChart start note (#4102)', () => {
  it('says when the realized series starts', () => {
    const html = render('2026-08-26');
    expect(html).toContain('data-testid="contribution-start-note"');
    expect(html).toContain('Finalized per-position attribution starts 2026-08-26');
  });

  it('stays silent when there is no realized start', () => {
    expect(render(null)).not.toContain('contribution-start-note');
    expect(render(undefined)).not.toContain('contribution-start-note');
  });

  it('stays silent when the series starts on the first plotted day', () => {
    const html = render('2026-08-24');
    expect(html).not.toContain('contribution-start-note');
  });

  it('stays silent while the snapshot is too short to chart', () => {
    const html = renderToStaticMarkup(
      createElement(PortfolioContributionChart, {
        points: [points[0]],
        benchmark: null,
        startsOn: '2026-08-26',
      })
    );
    expect(html).not.toContain('contribution-start-note');
  });
});
