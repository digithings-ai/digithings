import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import type { FxConsensusSnapshotRow } from '@/lib/twelve-x/types';
import ConsensusBoard from './ConsensusBoard';
import { TwelveXProvider, type TwelveXContextValue } from './context';

const ctx: TwelveXContextValue = {
  runDate: '2026-06-22',
  crossLink: () => {},
  openBrief: () => {},
  openIdea: () => {},
  watchlist: {
    items: [],
    has: () => false,
    toggle: () => {},
    clear: () => {},
    filterOn: false,
    setFilterOn: () => {},
  },
};

function row(currency: string, run_date: string, score: number): FxConsensusSnapshotRow {
  return {
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
  } as FxConsensusSnapshotRow;
}

const DATES = ['2026-06-16', '2026-06-17', '2026-06-18', '2026-06-19', '2026-06-20', '2026-06-22'];

function render(series: FxConsensusSnapshotRow[], disputed?: ReadonlySet<string>): string {
  return renderToStaticMarkup(
    <TwelveXProvider value={ctx}>
      <ConsensusBoard series={series} disputedCurrencies={disputed} />
    </TwelveXProvider>,
  );
}

describe('ConsensusBoard', () => {
  it('says the board is empty instead of drawing an empty list', () => {
    const html = render([]);
    expect(html).toContain('No consensus history yet');
    expect(html).not.toContain('aria-label="Consensus by currency"');
  });

  it('carries a screen-reader summary of every row', () => {
    const series = DATES.flatMap((d, i) => [row('EUR', d, 0.5 + i * 0.1), row('JPY', d, -1)]);
    const html = render(series);
    expect(html).toMatch(/<p class="sr-only">Consensus board, trailing 5-run average per currency: [^<]*EUR[^<]*JPY/);
  });

  it('draws a sparkline with enough runs and a dash with fewer than five', () => {
    const series = [
      ...DATES.map((d, i) => row('EUR', d, 0.5 + i * 0.1)),
      ...DATES.slice(-3).map((d) => row('JPY', d, -1)),
    ];
    const html = render(series);
    expect(html).toContain('EUR consensus over the last 6 runs');
    expect(html).not.toContain('JPY consensus over the last');
    const jpy = html.slice(html.indexOf('data-ccy="JPY"'));
    expect(jpy).toContain('title="Fewer than 5 runs — no trend drawn"');
  });

  it('flags disputed currencies with an announced marker, and only those', () => {
    const series = DATES.flatMap((d) => [row('EUR', d, 1), row('JPY', d, -1)]);
    const html = render(series, new Set(['JPY']));
    expect(html).toContain('data-ccy="JPY" data-disputed="true"');
    expect(html).not.toContain('data-ccy="EUR" data-disputed');
    expect(html).toContain('<span class="sr-only">, disputed by the data</span>');
    expect(html.match(/disputed by the data/g)).toHaveLength(1);
  });
});
