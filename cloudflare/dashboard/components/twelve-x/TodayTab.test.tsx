import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { G10_CURRENCIES } from '@/lib/twelve-x/types';
import type {
  FxBriefRow,
  FxConsensusDivergence,
  FxConsensusSnapshotRow,
  FxEconomicCalendarRow,
  FxTradeIdeaRow,
} from '@/lib/twelve-x/types';
import { TwelveXProvider, type TwelveXContextValue } from './context';
import TodayTab from './TodayTab';

/** Minimal context plumbing so TodayTab + its children can mount under SSR. */
const ctx: TwelveXContextValue = {
  runDate: '2026-06-22',
  crossLink: () => {},
  openBrief: () => {},
  watchlist: {
    items: [],
    has: () => false,
    toggle: () => {},
    clear: () => {},
    filterOn: false,
    setFilterOn: () => {},
  },
};

/** A 6-run ascending consensus series for every G10 currency (full markers). */
function tenCurrencySeries(): FxConsensusSnapshotRow[] {
  const dates = [
    '2026-06-17',
    '2026-06-18',
    '2026-06-19',
    '2026-06-20',
    '2026-06-21',
    '2026-06-22',
  ];
  const rows: FxConsensusSnapshotRow[] = [];
  G10_CURRENCIES.forEach((currency, ci) => {
    dates.forEach((run_date, di) => {
      const score = (ci % 2 === 0 ? 1 : -1) * (0.3 + di * 0.2);
      rows.push({
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
      });
    });
  });
  return rows;
}

function briefsFixture(): FxBriefRow[] {
  return [
    {
      run_date: '2026-06-22',
      source_file: 'desk-a.md',
      source_url: null,
      document_title: 'Dollar smile intact into Q3',
      broker_name: 'Acme Macro',
      analyst_names: ['J. Doe'],
      report_date: '2026-06-22',
      trader_relevance: 'high',
      central_thesis: 'USD stays bid as growth differentials widen.',
      brief_markdown: null,
      currency_views: [{ currency: 'USD', direction: 'bullish', conviction: 'high' }],
      risk_events: [],
      macro_themes: [],
      positioning_signals: [],
    },
    {
      run_date: '2026-06-22',
      source_file: 'desk-b.md',
      source_url: null,
      document_title: 'Euro range to hold',
      broker_name: 'Beta FX',
      analyst_names: null,
      report_date: '2026-06-21',
      trader_relevance: 'medium',
      central_thesis: 'EUR capped by soft PMIs.',
      brief_markdown: null,
      currency_views: [{ currency: 'EUR', direction: 'neutral', conviction: 'medium' }],
      risk_events: [],
      macro_themes: [],
      positioning_signals: [],
    },
    {
      run_date: '2026-06-22',
      source_file: 'desk-c.md',
      source_url: null,
      document_title: 'Yen sensitivity rises into BOJ',
      broker_name: 'Gamma Markets',
      analyst_names: null,
      report_date: '2026-06-21',
      trader_relevance: 'high',
      central_thesis: 'JPY remains sensitive to policy normalization signals.',
      brief_markdown: null,
      currency_views: [{ currency: 'JPY', direction: 'bearish', conviction: 'medium' }],
      risk_events: [],
      macro_themes: [],
      positioning_signals: [],
    },
  ];
}

function eventsFixture(): FxEconomicCalendarRow[] {
  return [
    {
      id: 1,
      external_id: 'evt-1',
      event_date: '2026-06-22',
      event_time: '12:30',
      country: 'US',
      event_name: 'Core PCE Price Index',
      category: 'inflation',
      impact: 'high',
      actual: null,
      forecast: '2.6%',
      prior: '2.7%',
      event_datetime_utc: '2026-06-22T12:30:00Z',
    },
    {
      id: 2,
      external_id: 'evt-2',
      event_date: '2026-06-22',
      event_time: '14:00',
      country: 'EU',
      event_name: 'ECB President Speech',
      category: 'central-bank',
      impact: 'medium',
      actual: null,
      forecast: null,
      prior: null,
      event_datetime_utc: '2026-06-22T14:00:00Z',
    },
  ];
}

function render(
  divergenceByCurrency: Record<string, FxConsensusDivergence> = {},
  tradeIdeas: FxTradeIdeaRow[] = [],
): string {
  return renderToStaticMarkup(
    <TwelveXProvider value={ctx}>
      <TodayTab
        digest={null}
        tradeIdeas={tradeIdeas}
        confluence={[]}
        briefs={briefsFixture()}
        events={eventsFixture()}
        series={tenCurrencySeries()}
        divergenceByCurrency={divergenceByCurrency}
        onSeeAllBriefs={() => {}}
      />
    </TwelveXProvider>,
  );
}

describe('TodayTab layout (Task 2.2)', () => {
  it('renders the TodayConsensusChart ("Consensus")', () => {
    expect(render()).toContain('Consensus');
  });

  it('renders at least three brief cards in an internally scrollable region', () => {
    const html = render();
    expect(html).toContain('Broker briefs');
    expect(html).toContain('Dollar smile intact into Q3');
    expect(html).toContain('Euro range to hold');
    expect(html).toContain('Yen sensitivity rises into BOJ');
    expect(html).toContain('aria-label="Broker brief cards"');
    expect(html).toContain('overflow-y-auto');
  });

  it('renders the full-width EventsTimeline (single-day) below', () => {
    const html = render();
    // The timeline mounts the reusable EventsTimeline scroll container.
    expect(html).toContain('tl-scroll');
    // The heading's apostrophe is rendered as a typographic ’ (&rsquo;).
    expect(html).toContain('Today’s timeline');
    // Today's events become positioned timeline cards (not the old list tile).
    expect(html).toContain('tl-card');
  });

  it('does NOT render MoversStrip nor the old "What changed" tile', () => {
    const html = render();
    expect(html).not.toContain('What changed');
    // `snap-x` is unique to MoversStrip's scroller.
    expect(html).not.toContain('snap-x');
    // The removed compact events tile titled "Today's events" is gone (it used
    // a typographic apostrophe, so check that exact rendered form).
    expect(html).not.toContain('Today’s events');
  });


  it('stacks digest → trade ideas → consensus on the left with a wider briefs rail', () => {
    const html = render();
    expect(html).toContain('today-main');
    expect(html).toContain('lg:grid-cols-[minmax(0,0.95fr)_minmax(0,1.25fr)]');
    // Digest precedes trade ideas heading in markup (left stack order).
    const digestIdx = html.indexOf('Digest brief');
    const ideasIdx = html.indexOf('Today’s trade ideas');
    const consensusIdx = html.indexOf('Consensus');
    expect(digestIdx).toBeGreaterThan(0);
    expect(ideasIdx).toBeGreaterThan(digestIdx);
    expect(consensusIdx).toBeGreaterThan(ideasIdx);
    // Briefs rail still height-matches the left stack on desktop;
    // mobile keeps a nested-scroll max-height.
    expect(html).toContain('lg:relative lg:self-stretch');
    expect(html).toContain('lg:absolute lg:inset-0');
    expect(html).toContain('max-h-[32rem]');
    expect(html).toContain('lg:max-h-none');
    // Single gap source — flat card list (date stamped on each card, no
    // interstitial headers that stacked space-y + mb + nested gap).
    expect(html).toContain('flex flex-col gap-2');
    expect(html).not.toContain('space-y-3');
    expect(html).not.toContain('mb-2 font-mono text-[10.5px]');
  });

  it('keeps even card spacing when briefs span multiple report dates', () => {
    const html = render();
    // Fixture spans two dates (06-22 and 06-21). Markup must use one gap-2
    // list with dates on cards — no per-date heading wrappers.
    const scrollerStart = html.indexOf('aria-label="Broker brief cards"');
    expect(scrollerStart).toBeGreaterThan(0);
    const scrollerChunk = html.slice(scrollerStart, scrollerStart + 3500);
    expect(scrollerChunk).toContain('flex flex-col gap-2');
    expect(scrollerChunk.match(/<ul /g)?.length ?? 0).toBe(1);
    expect(scrollerChunk).not.toContain('space-y-');
    expect(scrollerChunk).not.toContain('<h3');
    // Dates remain visible as per-card stamps (newest group still first).
    expect(scrollerChunk).toContain('2026-06-22');
    expect(scrollerChunk).toContain('2026-06-21');
  });

  it('groups broker briefs by effective date (report_date ?? run_date) newest-first', () => {
    const html = render();
    // Requirement 5: briefs must expose dates and group by report_date ?? run_date.
    // Fixture has desk-a (report_date 2026-06-22) and desk-b (report_date 2026-06-21).
    expect(html).toContain('2026-06-22');
    expect(html).toContain('2026-06-21');
    // Groups appear newest-first, so 06-22 precedes 06-21 in markup order.
    const idx22 = html.indexOf('2026-06-22');
    const idx21 = html.indexOf('2026-06-21');
    expect(idx22).toBeGreaterThan(0);
    expect(idx21).toBeGreaterThan(idx22);
  });

  it('shows the disputes line when trade ideas touch divergent currencies', () => {
    const tradeIdeas: FxTradeIdeaRow[] = [
      {
        run_date: '2026-06-22',
        rank: 1,
        pair: 'EUR/USD',
        direction: 'short',
        title: 'EUR short',
        thesis: '',
        catalyst: '',
        levels: [],
        citations: [],
        as_of: '2026-06-22T12:00:00Z',
      },
    ];
    const html = render(
      {
        EUR: {
          currency: 'EUR',
          consensusScore: 1.5,
          consensusTilt: 0.8,
          consensusAsOf: '2026-06-22T12:00:00Z',
          pmtSentiment: 'bearish',
          pmtScore: -1.25,
          pmtAsOf: '2026-06-15',
          gap: 2.75,
          isDivergent: true,
          snapshotId: null,
          rawSnapshot: null,
          streetStatement: 'Street score +1.50',
          pmtStatement: 'PMT Smart Bias Overall_Sentiment=bearish',
        },
      },
      tradeIdeas,
    );
    expect(html).toContain('data-disputes-line="true"');
    expect(html).toContain('The data disputes 1 of today');
  });
});
