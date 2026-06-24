import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import EventsTimeline, {
  packLanes,
  layoutDay,
  TL_LABEL_MIN,
  type TimelineEvent,
} from './EventsTimeline';

function ev(partial: Partial<TimelineEvent> & { time: string; durationMin: number }): TimelineEvent {
  return {
    date: '2026-06-22',
    currency: 'USD',
    title: 'Some event',
    impact: 'medium',
    ...partial,
  };
}

describe('packLanes', () => {
  it('places non-overlapping intervals in the same lane', () => {
    const items = [
      { startMin: 0, endMin: 30 },
      { startMin: 60, endMin: 90 },
    ];
    const lanes = items.map((it) => ({ ...it, lane: -1 }));
    const count = packLanes(lanes);
    expect(count).toBe(1);
    expect(lanes[0].lane).toBe(0);
    expect(lanes[1].lane).toBe(0);
  });

  it('places overlapping intervals in distinct lanes', () => {
    const lanes = [
      { startMin: 0, endMin: 60, lane: -1 },
      { startMin: 30, endMin: 90, lane: -1 },
      { startMin: 45, endMin: 120, lane: -1 },
    ];
    const count = packLanes(lanes);
    expect(count).toBe(3);
    // all three overlap one another → three distinct lanes
    expect(new Set(lanes.map((l) => l.lane)).size).toBe(3);
  });

  it('uses the rendered (clamped) end, so a short event with a wide body still gets its own lane', () => {
    // Two events 10 min apart, each only 5 min long. By raw duration they would
    // never overlap, but a clamped (label-min) width makes them visually collide.
    // packLanes must be fed the *rendered* end, so they land in different lanes.
    const lanes = [
      { startMin: 0, endMin: 120, lane: -1 }, // 5-min event rendered as a 120-min-wide box
      { startMin: 10, endMin: 130, lane: -1 },
    ];
    const count = packLanes(lanes);
    expect(count).toBe(2);
    expect(lanes[0].lane).not.toBe(lanes[1].lane);
  });
});

describe('layoutDay', () => {
  const pxPerHour = 60;

  it('positions a card at its start time with duration-derived width', () => {
    // 3h duration → 180px, comfortably above TL_LABEL_MIN so width is not clamped.
    const items = layoutDay([ev({ time: '02:00', durationMin: 180 })], pxPerHour);
    expect(items).toHaveLength(1);
    expect(items[0].x).toBe(120); // 2h * 60px
    expect(items[0].width).toBe(180); // 3h * 60px (un-clamped)
    expect(items[0].lane).toBe(0);
  });

  it('clamps a short-duration card to the label-min width', () => {
    const items = layoutDay([ev({ time: '00:00', durationMin: 5 })], pxPerHour);
    // 5min * (60/60) = 5px, far below the label minimum
    expect(items[0].width).toBeGreaterThanOrEqual(TL_LABEL_MIN);
  });

  it('does NOT collide a clamped short event with its near neighbour (the body-overlap bug)', () => {
    const items = layoutDay(
      [
        ev({ time: '00:00', durationMin: 5, title: 'Aaa' }),
        ev({ time: '00:10', durationMin: 5, title: 'Bbb' }),
      ],
      pxPerHour,
    );
    // both clamp to >= label-min; at 10min apart their boxes overlap, so they
    // must be on different lanes
    expect(items[0].lane).not.toBe(items[1].lane);
  });
});

function render(props: Parameters<typeof EventsTimeline>[0]): string {
  return renderToStaticMarkup(createElement(EventsTimeline, props));
}

describe('EventsTimeline component', () => {
  const events: TimelineEvent[] = [
    ev({ time: '08:30', durationMin: 30, currency: 'GBP', title: 'UK CPI', impact: 'high' }),
    ev({ time: '12:30', durationMin: 30, currency: 'USD', title: 'Jobless Claims', impact: 'medium' }),
    ev({ time: '18:00', durationMin: 90, currency: 'USD', title: 'FOMC', impact: 'high' }),
  ];

  it('renders one card per event', () => {
    const html = render({ events, mode: 'single', day: '2026-06-22' });
    const count = (html.match(/tl-card/g) || []).length;
    expect(count).toBe(events.length);
  });

  it('renders event titles', () => {
    const html = render({ events, mode: 'single', day: '2026-06-22' });
    expect(html).toContain('UK CPI');
    expect(html).toContain('FOMC');
  });

  it('applies impact classes', () => {
    const html = render({ events, mode: 'single', day: '2026-06-22' });
    expect(html).toContain('impact-high');
    expect(html).toContain('impact-med');
  });

  it('renders hour gridlines/labels', () => {
    const html = render({ events, mode: 'single', day: '2026-06-22' });
    expect(html).toContain('tl-grid');
    expect(html).toMatch(/\d{2}:00/);
  });

  it('renders multi-day mode with a scale control', () => {
    const multi: TimelineEvent[] = [
      ev({ date: '2026-06-22', time: '08:30', durationMin: 30, title: 'Day1' }),
      ev({ date: '2026-06-23', time: '09:00', durationMin: 30, title: 'Day2' }),
    ];
    const html = render({ events: multi, mode: 'multi' });
    expect(html).toContain('Day1');
    expect(html).toContain('Day2');
    // scale control present in multi mode
    expect(html.toLowerCase()).toContain('scale');
  });

  it('renders empty state with no events', () => {
    const html = render({ events: [], mode: 'single', day: '2026-06-22' });
    expect(html).not.toContain('tl-card');
  });
});
