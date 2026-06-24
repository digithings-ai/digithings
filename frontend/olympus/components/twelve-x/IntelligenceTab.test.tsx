import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import IntelligenceTab from './IntelligenceTab';
import { TwelveXProvider, type TwelveXContextValue } from './context';
import type {
  FxConfluenceSnapshotRow,
  IntelligenceWhy,
  IntelligenceWhyItem,
} from '@/lib/twelve-x/types';

const CTX: TwelveXContextValue = {
  runDate: '2026-06-24',
  crossLink: () => {},
  openBrief: () => {},
  watchlist: {
    has: () => false,
    toggle: () => {},
    items: [],
    clear: () => {},
  } as unknown as TwelveXContextValue['watchlist'],
};

const confluence = (over: Partial<FxConfluenceSnapshotRow> = {}): FxConfluenceSnapshotRow => ({
  run_date: '2026-06-24',
  rank: 1,
  title: 'USD long into PCE',
  currency: 'USD',
  direction: 'long',
  score: 0.8,
  components: {
    consensus_strength: 0.84,
    event_alignment: 0.8,
    recency: 1.0,
    breadth: 0.85,
    n_brokers: 17,
    days_to_catalyst: 0,
    timeframe: '1-3M',
  },
  brief_keys: [],
  as_of: '2026-06-24T00:00:00Z',
  ...over,
});

const whyItem = (over: Partial<IntelligenceWhyItem> = {}): IntelligenceWhyItem => ({
  currency: 'USD',
  rank: 1,
  direction: 'long',
  title: 'USD long into PCE',
  score: 0.8,
  components: {
    consensus_strength: 0.84,
    event_alignment: 0.8,
    recency: 1.0,
    breadth: 0.85,
    n_brokers: 17,
    days_to_catalyst: 0,
    timeframe: '1-3M',
  },
  consensus: {
    score: 1.1,
    confidence: 0.7,
    agreement: 0.66,
    tilt: 0.5,
    n_eff: 12,
    n_brokers: 17,
    n_views: 21,
    bullish_pct: 60,
    bearish_pct: 10,
    neutral_pct: 20,
    watch_pct: 10,
  },
  desks: [
    {
      broker: 'Atlas Macro',
      classification: 'active',
      relevance: 0.92,
      conviction: 'High',
      direction: 'bullish',
      reason: 'US rate resilience keeps the dollar bid.',
    },
  ],
  ...over,
});

function render(
  confluenceRows: FxConfluenceSnapshotRow[],
  why: IntelligenceWhy
): string {
  return renderToStaticMarkup(
    <TwelveXProvider value={CTX}>
      <IntelligenceTab
        confluence={confluenceRows}
        runDate="2026-06-24"
        events={[]}
        why={why}
        initialExpanded
      />
    </TwelveXProvider>
  );
}

describe('IntelligenceTab — why panels', () => {
  it('renders one why-panel per confluence idea, matched by currency', () => {
    const rows = [
      confluence({ rank: 1, currency: 'USD' }),
      confluence({ rank: 2, currency: 'JPY', title: 'JPY short', direction: 'short' }),
    ];
    const why: IntelligenceWhy = {
      runDate: '2026-06-24',
      items: [
        whyItem({ rank: 1, currency: 'USD' }),
        whyItem({
          rank: 2,
          currency: 'JPY',
          title: 'JPY short',
          direction: 'short',
          desks: [
            {
              broker: 'Meridian FX',
              classification: 'active',
              relevance: 0.9,
              conviction: 'High',
              direction: 'bearish',
              reason: 'Carry dynamics dominate.',
            },
          ],
        }),
      ],
    };
    const html = render(rows, why);
    // both cards render their Tier-3 desks (panel mapped to the right currency)
    expect(html).toContain('Atlas Macro');
    expect(html).toContain('Meridian FX');
    expect(html).toContain('Carry dynamics dominate.');
    // two waterfalls
    expect(html.match(/Tier 1/g)?.length).toBe(2);
  });

  it('still renders the card header + score + ComponentBar alongside the panel', () => {
    const html = render([confluence()], { runDate: '2026-06-24', items: [whyItem()] });
    expect(html).toContain('USD');
    expect(html).toContain('Confluence score');
    // the why panel's synthesized label is present
    expect(html).toContain('synthesized — would require generation');
  });

  it('renders a card without a panel when no matching why-item exists', () => {
    const html = render([confluence({ currency: 'CHF' })], { runDate: '2026-06-24', items: [] });
    expect(html).toContain('CHF');
    // no tiers since there is no why item
    expect(html).not.toContain('Tier 1');
  });
});
