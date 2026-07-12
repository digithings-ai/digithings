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
    // The two view buttons are present (data-evtview hooks, demo-faithful).
    expect(html).toContain('data-evtview="list"');
    expect(html).toContain('data-evtview="timeline"');
    // Their labels render.
    expect(html).toContain('>List<');
    expect(html).toContain('>Timeline<');
    // The Calendar view is gone entirely.
    expect(html).not.toContain('data-evtview="calendar"');
    expect(html).not.toContain('>Calendar<');
    expect(html).not.toContain('cal-grid');
  });

  it('defaults to the List view: grouped-by-day rows render', () => {
    const html = render();
    // The grouped-by-day list shows each event_name and a day header.
    expect(html).toContain('Core PCE Price Index');
    expect(html).toContain('ECB President Speech');
    expect(html).toContain('RBA Rate Decision');
    // The List button is marked active.
    expect(html).toContain('data-evtview="list" aria-pressed="true"');
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
    // Timeline button is the active one.
    expect(html).toContain('data-evtview="timeline" aria-pressed="true"');
  });

  it('renders an empty state in List view with no events', () => {
    const html = render({ events: [] });
    expect(html).toContain('No upcoming economic events');
  });
});

describe('EventsTab event-detail slide-over', () => {
  it('opens the detail slide-over when initialSelectedId targets an event', () => {
    const html = render({ initialSelectedId: '1' });
    // The slide-over dialog is rendered with the targeted event's detail.
    expect(html).toContain('role="dialog"');
    expect(html).toContain('aria-modal="true"');
    // The selected event's title is shown inside the panel.
    expect(html).toContain('Core PCE Price Index');
  });

  it('does not render the slide-over when nothing is selected', () => {
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
  it('renders the timeline cards as clickable buttons in timeline view', () => {
    const html = render({ initialView: 'timeline' });
    // The tl-card is now a button element wired to onSelect.
    expect(html).toMatch(/<button[^>]*tl-card/);
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
