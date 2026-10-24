import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import EventsTab from './EventsTab';
import { eventsToTimeline, layoutDay, type TimelineEvent } from './EventsTimeline';
import type { FxEconomicCalendarRow, FxEventSnapshotRow } from '@/lib/twelve-x/types';

/** Minimal calendar-row factory; only the fields the tab reads matter. */
function row(
  partial: Partial<FxEconomicCalendarRow> & { event_date: string },
): FxEconomicCalendarRow {
  return {
    id: Math.floor(Math.random() * 1e9),
    external_id: 'x',
    event_time: null,
    country: 'US',
    event_name: 'Some event',
    category: 'macro',
    impact: 'medium',
    actual: null,
    forecast: null,
    prior: null,
    event_datetime_utc: null,
    ...partial,
  };
}

const events: FxEconomicCalendarRow[] = [
  row({
    id: 1,
    event_date: '2026-06-22',
    event_time: '12:30',
    country: 'US',
    event_name: 'Core PCE Price Index',
    impact: 'high',
    prior: '2.7%',
    forecast: '2.6%',
    actual: null,
    event_datetime_utc: '2026-06-22T12:30:00Z',
  }),
  row({
    id: 2,
    event_date: '2026-06-22',
    event_time: '14:00',
    country: 'EU',
    event_name: 'ECB President Speech',
    impact: 'medium',
    prior: null,
    forecast: null,
    actual: null,
    event_datetime_utc: '2026-06-22T14:00:00Z',
  }),
  row({
    id: 3,
    event_date: '2026-06-23',
    event_time: '01:30',
    country: 'AU',
    event_name: 'RBA Rate Decision',
    impact: 'high',
    prior: '3.85%',
    forecast: '3.85%',
    actual: null,
    event_datetime_utc: '2026-06-23T01:30:00Z',
  }),
];

const noOpinions: FxEventSnapshotRow[] = [];

/** Create a minimal opinion snapshot for testing evidence-based interactivity. */
function opinion(
  partial: Partial<FxEventSnapshotRow> & { event_key: string },
): FxEventSnapshotRow {
  return {
    run_date: '2026-06-22',
    event_name: 'Some Event',
    event_date: null,
    calendar_external_id: '',
    release_at: null,
    category: 'macro',
    currencies: [],
    mentions: 1,
    brokers: ['research Macro'],
    citations: [],
    as_of: '2026-06-22T00:00:00Z',
    ...partial,
  };
}

function render(props: Partial<Parameters<typeof EventsTab>[0]> = {}): string {
  return renderToStaticMarkup(
    createElement(EventsTab, {
      events,
      opinions: noOpinions,
      runDate: '2026-06-22',
      focus: null,
      ...props,
    }),
  );
}

describe('EventsTab view switcher (Task 4.2)', () => {
  it('renders a List | Timeline segmented control (no Calendar)', () => {
    const html = render();
    // The view toggle is the canonical shared SegmentedControl (#4306).
    expect(html).toContain('data-slot="segmented"');
    expect(html).toContain('aria-label="Events view"');
    expect(html).toContain('>List</button>');
    expect(html).toContain('>Timeline</button>');
    // The Calendar view is gone entirely.
    expect(html).not.toContain('>Calendar<');
    expect(html).not.toContain('cal-grid');
  });

  it('defaults to the List view: grouped-by-day rows render', () => {
    const html = render();
    // The grouped-by-day list shows each event_name and a day header.
    expect(html).toContain('Core PCE Price Index');
    expect(html).toContain('ECB President Speech');
    expect(html).toContain('RBA Rate Decision');
    // The List segment is marked active.
    expect(html).toMatch(/aria-pressed="true"[^>]*>List<\/button>/);
    // The default view is NOT the timeline Gantt nor the calendar grid.
    expect(html).not.toContain('tl-card');
    expect(html).not.toContain('cal-grid');
  });

  it('shows the prior value next to forecast/actual when present', () => {
    const html = render();
    // Core PCE has prior 2.7% — surfaced as a "Prior" figure beside Fcst/Act
    // (the value sits inside a tabular-nums span immediately after the label).
    expect(html).toMatch(/Prior[\s\S]{0,80}2\.7%/);
    // Forecast still shown.
    expect(html).toMatch(/Fcst[\s\S]{0,80}2\.6%/);
  });

  it('renders the Timeline Gantt when initialView="timeline"', () => {
    const html = render({ initialView: 'timeline' });
    // The reusable EventsTimeline mounts its scroll container + positioned cards.
    expect(html).toContain('tl-scroll');
    expect(html).toContain('tl-card');
    // Multi-day mode exposes the scale control.
    expect(html.toLowerCase()).toContain('scale');
    // Timeline segment is the active one.
    expect(html).toMatch(/aria-pressed="true"[^>]*>Timeline<\/button>/);
  });

  it('renders an empty state in List view with no events', () => {
    const html = render({ events: [] });
    expect(html).toContain('No economic releases have been ingested');
  });

  // #1753: the feed's forward horizon is shorter than this surface's 14-day window, so
  // the empty state is the normal state for days at a time. It must describe the FEED,
  // not assert that no macro releases exist — a claim a real 14-day window disproves.
  it('attributes the empty state to the feed rather than claiming there are no events', () => {
    for (const html of [render({ events: [] }), render({ events: [], initialView: 'timeline' })]) {
      expect(html).toContain('shared macro calendar feed does not currently cover this window');
      expect(html).not.toContain('No upcoming economic events in the next 14 days.');
    }
  });
});

describe('EventsTab event-detail slide-over (SSR shell)', () => {
  // The panel chrome is the shared Sheet (Base UI Dialog) whose popup lives in
  // a client-only portal — static SSR never paints it, open or closed. The
  // positive open-state wiring is covered by EventsTab.open-state.test.tsx
  // (happy-dom: seed + row click + Escape), the content by
  // EventDetailPanel.test.tsx, and the live dialog semantics by CDP.
  it('does not render the slide-over shell in static SSR', () => {
    const html = render();
    expect(html).not.toContain('aria-modal="true"');
  });

  it('makes each list event a clickable button (opens the panel, no inline expand)', () => {
    const html = render();
    // List rows are clickable buttons (open the slide-over) rather than disabled.
    expect(html).toContain('Core PCE Price Index');
    // The legacy inline expand container must be gone.
    expect(html).not.toContain('border-t border-hair/60');
  });
});

describe('EventsTab timeline wiring', () => {
  it('renders timeline cards as clickable buttons when they have evidence', () => {
    // Provide an opinion for the first event so it becomes selectable.
    const withOpinions = [
      opinion({
        event_key: 'core-pce',
        event_name: 'Core PCE Price Index',
        event_date: '2026-06-22',
        mentions: 2,
        brokers: ['Goldman', 'JPM'],
        citations: [
          {
            broker: 'Goldman',
            expected_outcome: 'In line',
            fx_impact: 'USD bid',
            source_file: 'gs.pdf',
            brief_key: 'gs',
          },
        ],
      }),
    ];
    const html = render({ initialView: 'timeline', opinions: withOpinions });
    // At least one tl-card should be a button (the one with evidence).
    expect(html).toMatch(/<button[^>]*tl-card/);
  });

  it('renders timeline cards as static divs when they have no evidence', () => {
    const html = render({ initialView: 'timeline', opinions: noOpinions });
    // All cards should be divs (no evidence = no interactivity).
    expect(html).toMatch(/<div[^>]*tl-card/);
    expect(html).not.toMatch(/<button[^>]*tl-card/);
  });
});

describe('EventsTab opinion matching across source-switched twins (#4739)', () => {
  // The calendar table is append-only across sources: a te- row retired by twin
  // cleanup (or hidden by read-model dedup) lives on as a gb- twin with the same
  // name+date but a different external_id. An opinion snapshot linked to the dead
  // te- id must still match the surviving gb- row via the name+date fallback —
  // otherwise the desk commentary silently disappears from the event.
  const gbRow = row({
    id: 101,
    event_date: '2026-09-29',
    event_time: '13:30',
    country: 'EU',
    event_name: 'CPI Flash Estimate y/y',
    external_id: 'gb-EU-2026-09-29-cpi-flash-estimate-y-y',
    event_datetime_utc: '2026-09-29T13:30:00Z',
  });
  const teOpinion = opinion({
    event_key: 'eu-cpi-flash-2026-09-29',
    event_name: 'CPI Flash Estimate y/y',
    event_date: '2026-09-29',
    calendar_external_id: 'te-EU-2026-09-29-spanish-flash-cpi-y-y',
    mentions: 7,
    brokers: ['Desk Alpha'],
  });

  it('matches an id-linked opinion to the surviving gb- twin via name+date fallback', () => {
    const html = render({ events: [gbRow], opinions: [teOpinion] });
    // The mentions badge only renders inside the evidence Button branch, i.e.
    // iff matchOpinions found the opinion for this row.
    expect(html).toContain('>7</span>');
  });

  it('does not match the fallback when name+date disagree', () => {
    const html = render({
      events: [gbRow],
      opinions: [{ ...teOpinion, event_name: 'Unrelated Release' }],
    });
    expect(html).not.toContain('>7</span>');
  });

  it('still prefers the exact external_id join when the linked row exists', () => {
    const teRow = row({
      id: 102,
      event_date: '2026-09-29',
      event_time: '09:30',
      country: 'EU',
      event_name: 'CPI Flash Estimate y/y',
      external_id: 'te-EU-2026-09-29-spanish-flash-cpi-y-y',
      event_datetime_utc: '2026-09-29T09:30:00Z',
    });
    const html = render({ events: [teRow, gbRow], opinions: [teOpinion] });
    // Both rows match (te- exactly, gb- via fallback) — the opinion stays
    // visible on either rather than orphaned from one.
    expect(html.match(/>7<\/span>/g)).toHaveLength(2);
  });
});

describe('eventsToTimeline shared mapper', () => {
  it('maps calendar rows to the timeline event shape', () => {
    const mapped = eventsToTimeline(events);
    expect(mapped).toHaveLength(3);
    const pce = mapped.find((e) => e.title === 'Core PCE Price Index')!;
    expect(pce.id).toBe('1');
    expect(pce.currency).toBe('US');
    expect(pce.impact).toBe('high');
    expect(pce.date).toBe('2026-06-22');
    // local clock derived from the UTC instant (HH:MM format)
    expect(pce.time).toMatch(/^\d{2}:\d{2}$/);
    // every mapped event carries a positive duration so it occupies a slot
    expect(pce.durationMin).toBeGreaterThan(0);
  });

  it('normalizes the feed impact to the 3-level scale (med -> medium)', () => {
    const mapped = eventsToTimeline([
      row({ id: 9, event_date: '2026-06-22', impact: 'med', event_name: 'X' }),
    ]);
    expect(mapped[0].impact).toBe('medium');
  });
});

describe('body-overlap fix holds for the multi-day timeline path', () => {
  it('places two near-adjacent short events with long titles on distinct lanes at >= label-min width', () => {
    // Two events 10 min apart on the SAME day, each only 5 min long, with long
    // titles. Raw duration would never overlap, but the label-min clamp widens
    // each box so they visually collide — layoutDay must lane-pack on the
    // rendered (clamped) width so they land on different lanes (Phase-1 fix).
    const sameDay: TimelineEvent[] = [
      { id: 'a', date: '2026-06-22', time: '00:00', durationMin: 5, currency: 'USD', title: 'A very long event title that overruns its slot', impact: 'high' },
      { id: 'b', date: '2026-06-22', time: '00:10', durationMin: 5, currency: 'EUR', title: 'Another very long event title that overruns', impact: 'medium' },
    ];
    const cards = layoutDay(sameDay, 64); // hour scale px/hour
    expect(cards).toHaveLength(2);
    // Both clamp to at least the label minimum width.
    for (const c of cards) expect(c.width).toBeGreaterThanOrEqual(88);
    // And, being visually overlapping, they sit on distinct lanes.
    expect(cards[0].lane).not.toBe(cards[1].lane);
  });
});

describe('day grouping is viewer-local, not UTC (#1753)', () => {
  it('files a UTC-tomorrow release under the local day its header shows', () => {
    // 01:30Z Aug 1 is 21:30 Jul 31 in New York. The tab groups on eventLocalDateKey, so
    // the header must read the LOCAL day — which is why the query bound in
    // `getUpcomingEvents` has to be the local date too, or this row is never fetched.
    const realTz = process.env.TZ;
    process.env.TZ = 'America/New_York';
    try {
      const html = renderToStaticMarkup(
        createElement(EventsTab, {
          events: [
            row({
              id: 42,
              event_date: '2026-08-01',
              event_datetime_utc: '2026-08-01T01:30:00Z',
              event_name: 'Late Tape Release',
            }),
          ],
          opinions: noOpinions,
          runDate: '2026-07-31',
          focus: null,
        }),
      );
      // Scoped to the day header's own text node: the row's event_date is 2026-08-01, so
      // a 2026-07-31 header can only have come from eventLocalDateKey.
      expect(html).toContain('>2026-07-31<');
      expect(html).not.toContain('>2026-08-01<');
    } finally {
      if (realTz === undefined) delete process.env.TZ;
      else process.env.TZ = realTz;
    }
  });
});

// The dedicated terminal entry lives in the sidebar now (#4204); the
// twelve-x macro surfaces must not carry their own Gloomberb links.
describe('EventsTab — no Gloomberb shortcut (#4204)', () => {
  it('does not link the macro calendar header out to Gloomberb', () => {
    const html = render({});
    expect(html).not.toContain('gloomberb-terminal-link');
    expect(html).not.toContain('term.gloom.sh');
  });
});
