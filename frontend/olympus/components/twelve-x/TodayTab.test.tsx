import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { G10_CURRENCIES } from '@/lib/twelve-x/types';
import type {
  FxBriefRow,
  FxConsensusSnapshotRow,
  FxEconomicCalendarRow,
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

function render(): string {
  return renderToStaticMarkup(
    <TwelveXProvider value={ctx}>
      <TodayTab
        digest={null}
        tradeIdeas={[]}
        confluence={[]}
        briefs={briefsFixture()}
        events={eventsFixture()}
        series={tenCurrencySeries()}
        onSeeAllBriefs={() => {}}
      />
    </TwelveXProvider>,
  );
}

describe('TodayTab layout (Task 2.2)', () => {
  it('renders the TodayConsensusChart ("Consensus average")', () => {
    expect(render()).toContain('Consensus average');
  });

  it('renders a scrollable broker-briefs list with the brief content', () => {
    const html = render();
    expect(html).toContain('Broker briefs');
    expect(html).toContain('Dollar smile intact into Q3');
    expect(html).toContain('Euro range to hold');
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

  it('height-matches the consensus + briefs columns (stretch + scroll markup)', () => {
    const html = render();
    // The mid row is a stretch grid; the briefs column flexes + scrolls.
    expect(html).toContain('today-mid');
    expect(html).toContain('items-stretch');
    expect(html).toContain('overflow-y-auto');
  });
});
