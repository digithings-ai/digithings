import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, describe, expect, it, vi } from 'vitest';
import EventsCalendar, { buildMonthGrid } from './EventsCalendar';
import type { FxEconomicCalendarRow } from '@/lib/twelve-x/types';

/** Minimal calendar-row factory; only the fields the grid reads matter. */
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

describe('buildMonthGrid', () => {
  // June 2026: the 1st is a Monday, so a Sunday-start grid has one leading
  // (May 31) trailing-edge cell; 30 days → spills into July. 6 weeks of 7 = 42.
  const events: FxEconomicCalendarRow[] = [
    row({ event_date: '2026-06-01', impact: 'high' }),
    row({ event_date: '2026-06-01', impact: 'low' }),
    row({ event_date: '2026-06-15', impact: 'medium' }),
    row({ event_date: '2026-06-15', impact: 'high' }),
    row({ event_date: '2026-06-15', impact: 'high' }),
    // an event outside the month must not bucket into any in-month cell
    row({ event_date: '2026-07-04', impact: 'high' }),
  ];

  it('produces whole weeks of 7 cells', () => {
    const grid = buildMonthGrid('2026-06', events);
    expect(grid.year).toBe(2026);
    expect(grid.month).toBe(6);
    expect(grid.weeks.length).toBeGreaterThanOrEqual(4);
    for (const week of grid.weeks) {
      expect(week).toHaveLength(7);
    }
  });

  it('flags leading/trailing days as not in-month and the rest in-month', () => {
    const grid = buildMonthGrid('2026-06', events);
    const cells = grid.weeks.flat();
    // The first cell of June 2026 (a Monday-1st) is the prior Sunday, May 31.
    expect(cells[0].inMonth).toBe(false);
    expect(cells[0].date).toBe('2026-05-31');
    // Exactly 30 cells are flagged in-month (June has 30 days).
    expect(cells.filter((c) => c.inMonth).length).toBe(30);
    // Every in-month cell carries an ISO date within the month.
    for (const c of cells.filter((c) => c.inMonth)) {
      expect(c.date.startsWith('2026-06-')).toBe(true);
    }
  });

  it('buckets events to the correct day with counts and impact tallies', () => {
    const grid = buildMonthGrid('2026-06', events);
    const cells = grid.weeks.flat();
    const find = (iso: string) => cells.find((c) => c.date === iso)!;

    const jun1 = find('2026-06-01');
    expect(jun1.count).toBe(2);
    expect(jun1.impacts.high).toBe(1);
    expect(jun1.impacts.low).toBe(1);
    expect(jun1.impacts.medium).toBe(0);

    const jun15 = find('2026-06-15');
    expect(jun15.count).toBe(3);
    expect(jun15.impacts.high).toBe(2);
    expect(jun15.impacts.medium).toBe(1);

    // A day with no events has a zero count.
    expect(find('2026-06-02').count).toBe(0);
  });

  it('does not bucket out-of-month events into any in-month cell', () => {
    const grid = buildMonthGrid('2026-06', events);
    const totalInMonth = grid.weeks
      .flat()
      .filter((c) => c.inMonth)
      .reduce((sum, c) => sum + c.count, 0);
    // 5 of the 6 events fall in June; the July 4 event is excluded.
    expect(totalInMonth).toBe(5);
  });

  describe('buckets by the local instant date, not the raw event_date', () => {
    // 2026-06-10T23:30Z crosses midnight in a UTC+14 zone (→ Jun 11 local) but
    // NOT in a UTC-12 zone (→ Jun 10 local). The grid must bucket by
    // eventLocalDateKey (the local instant day), so the populated cell tracks the
    // *local* day. A buggy grid that read the raw `event_date` string ('2026-06-10')
    // would always land on Jun 10 and fail the UTC+14 assertion below. We pin TZ
    // via vi.stubEnv so the assertion is deterministic regardless of runner tz.
    afterEach(() => vi.unstubAllEnvs());

    it('lands on the next local day in a far-east timezone (UTC+14)', () => {
      vi.stubEnv('TZ', 'Pacific/Kiritimati');
      const e = row({ event_date: '2026-06-10', event_datetime_utc: '2026-06-10T23:30:00Z' });
      const grid = buildMonthGrid('2026-06', [e]);
      const withCount = grid.weeks.flat().filter((c) => c.count > 0);
      expect(withCount).toHaveLength(1);
      expect(withCount[0].count).toBe(1);
      // Diverges from the raw event_date ('2026-06-10') — this is what the
      // raw-event_date foil cannot satisfy.
      expect(withCount[0].date).toBe('2026-06-11');
    });

    it('stays on the same local day in a far-west timezone (UTC-12)', () => {
      vi.stubEnv('TZ', 'Etc/GMT+12');
      const e = row({ event_date: '2026-06-10', event_datetime_utc: '2026-06-10T23:30:00Z' });
      const grid = buildMonthGrid('2026-06', [e]);
      const withCount = grid.weeks.flat().filter((c) => c.count > 0);
      expect(withCount).toHaveLength(1);
      expect(withCount[0].count).toBe(1);
      expect(withCount[0].date).toBe('2026-06-10');
    });
  });
});

function render(props: Parameters<typeof EventsCalendar>[0]): string {
  return renderToStaticMarkup(createElement(EventsCalendar, props));
}

describe('EventsCalendar component', () => {
  const events: FxEconomicCalendarRow[] = [
    row({ event_date: '2026-06-01', impact: 'high', country: 'US', event_name: 'ISM' }),
    row({ event_date: '2026-06-15', impact: 'medium', country: 'EU', event_name: 'ECB' }),
  ];

  it('pins the rendered month with initialMonth', () => {
    const html = render({ events, initialMonth: '2026-06' });
    // The grid renders day numbers 1..30 for June.
    expect(html).toContain('>1<');
    expect(html).toContain('>30<');
    // Weekday headers present.
    expect(html).toContain('Sun');
    expect(html).toContain('Sat');
  });

  it('renders the seven weekday column headers', () => {
    const html = render({ events, initialMonth: '2026-06' });
    for (const d of ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']) {
      expect(html).toContain(d);
    }
  });

  it('marks days that have events with an event indicator', () => {
    const html = render({ events, initialMonth: '2026-06' });
    // Days with events are clickable cells carrying the has-evt marker class.
    expect(html).toContain('has-evt');
    // A compact count indicator appears (e.g. "1 event").
    expect(html).toMatch(/1\s*event/);
  });

  it('renders a grid container', () => {
    const html = render({ events, initialMonth: '2026-06' });
    expect(html).toContain('cal-grid');
  });

  it('renders even when there are no events', () => {
    const html = render({ events: [], initialMonth: '2026-06' });
    expect(html).toContain('cal-grid');
    expect(html).not.toContain('has-evt');
  });
});
