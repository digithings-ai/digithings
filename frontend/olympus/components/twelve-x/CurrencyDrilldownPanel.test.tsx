import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import type { IntelligenceWhyItem } from '@/lib/twelve-x/types';
import type { ConsensusCurrencyRow } from '@/lib/twelve-x/consensus-view';
import type { FxBriefRow } from '@/lib/twelve-x/types';
import { CurrencyDrilldownPanelBody } from './CurrencyDrilldownPanel';

function mockConsensusRow(currency: string, overrides: Partial<ConsensusCurrencyRow> = {}): ConsensusCurrencyRow {
  return {
    currency,
    avgNow: 1.2,
    actualNow: 1.3,
    avgYesterday: 1.1,
    avgAgo: 1.0,
    momentum: 0.1,
    label: 'Bullish lean',
    priorActual: 1.2,
    priorChange: 0.1,
    ...overrides,
  };
}

function mockIntelligenceItem(currency: string): IntelligenceWhyItem {
  return {
    currency,
    rank: 1,
    direction: 'bullish',
    title: `${currency} trade idea`,
    score: 0.85,
    components: {
      consensus_strength: 0.8,
      event_alignment: 0.9,
      recency: 0.85,
      breadth: 0.8,
      n_brokers: 5,
      days_to_catalyst: 3,
      timeframe: 'medium',
    },
    consensus: {
      score: 1.3,
      confidence: 0.75,
      agreement: 0.7,
      tilt: 0.1,
      n_eff: 8.5,
      n_brokers: 5,
      n_views: 10,
      bullish_pct: 0.6,
      bearish_pct: 0.3,
      neutral_pct: 0.05,
      watch_pct: 0.05,
    },
    desks: [
      {
        broker: 'Broker A',
        classification: 'active',
        relevance: 0.95,
        conviction: 'high',
        direction: 'bullish',
        reason: 'Strong fundamentals',
      },
      {
        broker: 'Broker B',
        classification: 'active',
        relevance: 0.85,
        conviction: 'medium',
        direction: 'bearish',
        reason: 'Technical breakout',
      },
      {
        broker: 'Superseded Broker',
        classification: 'superseded',
        relevance: 0.4,
        conviction: 'low',
        direction: 'bearish',
        reason: 'Superseded by a newer opinion.',
      },
    ],
  };
}

function mockBrief(sourceFile: string, currency: string): FxBriefRow {
  return {
    run_date: '2026-06-22',
    source_file: sourceFile,
    source_url: null,
    document_title: null,
    broker_name: 'Broker A',
    analyst_names: ['Analyst 1'],
    report_date: '2026-06-21',
    trader_relevance: 'high',
    central_thesis: `${currency} outlook`,
    brief_markdown: `# ${currency} Analysis\n\nBullish on ${currency}`,
    currency_views: [{ currency, direction: 'bullish' }],
    risk_events: null,
    macro_themes: null,
    positioning_signals: null,
  };
}

describe('CurrencyDrilldownPanelBody', () => {
  it('renders currency header and score explanation', () => {
    const html = renderToStaticMarkup(
      createElement(CurrencyDrilldownPanelBody, {
        currency: 'USD',
        consensusRow: mockConsensusRow('USD'),
        intelligenceItem: mockIntelligenceItem('USD'),
        relevantBriefs: [],
        onOpenBrief: () => {},
      }),
    );

    expect(html).toContain('USD');
    expect(html).toContain('Bullish lean');
    expect(html).toContain('1.3'); // actualNow
    expect(html).toContain('1.2'); // avgNow (5-run)
  });

  it('shows desk opinion counts and split', () => {
    const intelligence = mockIntelligenceItem('EUR');
    intelligence.consensus!.bullish_pct = 60;
    intelligence.consensus!.bearish_pct = 30;
    const html = renderToStaticMarkup(
      createElement(CurrencyDrilldownPanelBody, {
        currency: 'EUR',
        consensusRow: mockConsensusRow('EUR'),
        intelligenceItem: intelligence,
        relevantBriefs: [],
        onOpenBrief: () => {},
      }),
    );

    expect(html).toContain('10'); // n_views
    expect(html).toContain('5'); // n_brokers (desks)
    expect(html).toContain('60%'); // bullish_pct
    expect(html).toContain('30%'); // bearish_pct
  });

  it('uses the raw prior-run change rather than the trailing-average delta', () => {
    const html = renderToStaticMarkup(
      createElement(CurrencyDrilldownPanelBody, {
        currency: 'USD',
        consensusRow: mockConsensusRow('USD', {
          avgNow: 1.2,
          avgYesterday: 1.1,
          priorChange: 0.25,
        }),
        intelligenceItem: mockIntelligenceItem('USD'),
        relevantBriefs: [],
        onOpenBrief: () => {},
      }),
    );

    expect(html).toContain('0.25');
  });

  it('displays confluence score and components', () => {
    const html = renderToStaticMarkup(
      createElement(CurrencyDrilldownPanelBody, {
        currency: 'GBP',
        consensusRow: mockConsensusRow('GBP'),
        intelligenceItem: mockIntelligenceItem('GBP'),
        relevantBriefs: [],
        onOpenBrief: () => {},
      }),
    );

    expect(html).toContain('0.85'); // confluence score
    expect(html).toContain('Consensus strength');
    expect(html).toContain('0.8'); // consensus_strength component
  });

  it('lists desk opinions in scrollable section', () => {
    const html = renderToStaticMarkup(
      createElement(CurrencyDrilldownPanelBody, {
        currency: 'JPY',
        consensusRow: mockConsensusRow('JPY'),
        intelligenceItem: mockIntelligenceItem('JPY'),
        relevantBriefs: [],
        onOpenBrief: () => {},
      }),
    );

    expect(html).toContain('Broker A');
    expect(html).toContain('Broker B');
    expect(html).toContain('Strong fundamentals');
    expect(html).toContain('Technical breakout');
    expect(html).toContain('overflow-y-auto overscroll-contain pr-1 pb-1');
    expect(html).toContain('rounded-lg border border-hair');
    expect(html).toContain('border-accent/30 bg-accent/[0.05]');
    expect(html).toContain('capitalize text-accent');
    expect(html).toContain('border-warn/30 bg-warn/[0.05]');
    expect(html).toContain('capitalize text-warn');
    expect(html).not.toContain('Superseded Broker');
    expect(html).not.toContain('Superseded by a newer opinion.');
    expect(html).not.toContain('class="rounded border border-hair');
  });

  it('lists relevant briefs with open action', () => {
    const briefs = [
      mockBrief('brief1.md', 'CHF'),
      mockBrief('brief2.md', 'CHF'),
    ];

    const html = renderToStaticMarkup(
      createElement(CurrencyDrilldownPanelBody, {
        currency: 'CHF',
        consensusRow: mockConsensusRow('CHF'),
        intelligenceItem: mockIntelligenceItem('CHF'),
        relevantBriefs: briefs,
        onOpenBrief: () => {},
      }),
    );

    expect(html).toContain('brief1.md');
    expect(html).toContain('brief2.md');
    expect(html).toContain('Broker A');
    expect(html).toContain('w-full rounded-lg border border-hair');
  });

  it('shows em dash when no confluence data available', () => {
    const html = renderToStaticMarkup(
      createElement(CurrencyDrilldownPanelBody, {
        currency: 'CAD',
        consensusRow: mockConsensusRow('CAD'),
        intelligenceItem: null,
        relevantBriefs: [],
        onOpenBrief: () => {},
      }),
    );

    expect(html).toContain('CAD');
    expect(html).toContain('—'); // em dash for missing confluence
  });
});
