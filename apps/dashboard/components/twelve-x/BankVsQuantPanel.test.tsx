import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import type { ConsensusCurrencyRow } from '@/lib/twelve-x/consensus-view';
import type { FxConsensusDivergence } from '@/lib/twelve-x/types';
import BankVsQuantPanel, { buildBankVsQuantRows } from './BankVsQuantPanel';

function div(currency: string, partial: Partial<FxConsensusDivergence> = {}): FxConsensusDivergence {
  return {
    currency,
    consensusScore: 1.0,
    consensusTilt: 0.5,
    consensusAsOf: '2026-06-26T00:00:00Z',
    pmtSentiment: 'bearish',
    pmtScore: -1.0,
    pmtAsOf: '2026-06-21',
    gap: 2.0,
    isDivergent: true,
    snapshotId: null,
    rawSnapshot: null,
    streetStatement: 'Street leans bullish',
    pmtStatement: 'PMT leans bearish',
    ...partial,
  };
}

function row(currency: string): ConsensusCurrencyRow {
  return {
    currency,
    avgNow: 1.0,
    actualNow: 1.0,
    avgYesterday: 0.9,
    avgAgo: 0.8,
    momentum: 0.1,
    label: 'Bullish lean',
    priorActual: 0.9,
    priorChange: 0.1,
  };
}

describe('buildBankVsQuantRows', () => {
  it('sorts divergent-first, then gap descending', () => {
    const rows = buildBankVsQuantRows(
      {
        EUR: div('EUR', { isDivergent: true, gap: 1.0 }),
        GBP: div('GBP', { isDivergent: false, gap: 0.2 }),
        JPY: div('JPY', { isDivergent: true, gap: 2.5 }),
      },
      [row('EUR'), row('GBP'), row('JPY')],
    );
    expect(rows.map((r) => r.currency)).toEqual(['JPY', 'EUR', 'GBP']);
  });

  it('drops currencies without a divergence read', () => {
    const rows = buildBankVsQuantRows({ EUR: div('EUR') }, [row('EUR'), row('USD')]);
    expect(rows.map((r) => r.currency)).toEqual(['EUR']);
  });
});

describe('BankVsQuantPanel', () => {
  it('renders two score bars per row with divergent-first order', () => {
    const html = renderToStaticMarkup(
      createElement(BankVsQuantPanel, {
        divergenceByCurrency: {
          EUR: div('EUR', { consensusScore: 1.0, pmtScore: -1.0, gap: 2.0, isDivergent: true }),
          GBP: div('GBP', { consensusScore: 0.2, pmtScore: 0.1, gap: 0.1, isDivergent: false }),
        },
        consensusRows: [row('EUR'), row('GBP')],
      }),
    );
    expect(html).toContain('Bank vs quant · 1 divergent');
    // Divergent EUR heads the table.
    expect(html.indexOf('EUR')).toBeLessThan(html.indexOf('GBP'));
    expect(html).toContain('DIV');
    expect(html).toContain('+1.00');
    expect(html).toContain('-1.00');
    // Two ConsensusScoreBar tracks per row → two dbar-track divs per currency row.
    expect(html.match(/dbar-track/g)?.length).toBe(4);
  });

  it('renders an empty state when there are no reads', () => {
    const html = renderToStaticMarkup(
      createElement(BankVsQuantPanel, { divergenceByCurrency: {}, consensusRows: [] }),
    );
    expect(html).toContain('No street-vs-quant reads for this run.');
  });
});
