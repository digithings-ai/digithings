'use client';

import { useLayoutEffect, useRef, useState } from 'react';
import { eventInstant, eventLocalDateKey } from '@/lib/twelve-x/fetch';
import type { FxEconomicCalendarRow } from '@/lib/twelve-x/types';

/**
 * Reusable horizontal Gantt timeline for macro events.
 *
 * Cards sit at their start time and span their duration; when they overlap they
 * stack into lanes. Ported from the frozen twelve-x visual spec's
 * `renderTimeline` / `packLanes`, with the known body-overlap bug fixed: card
 * width is clamped to a label-minimum AND lane-packing uses the *rendered*
 * (clamped) width — so a short-duration / long-label event no longer overruns
 * the box and no longer collides with its near neighbour.
 */

export type TimelineImpact = 'high' | 'medium' | 'low';

export interface TimelineEvent {
  id?: string;
  date: string;
  time: string; // "HH:MM"
  durationMin: number;
  currency: string;
  title: string;
  impact: TimelineImpact;
}

export interface TimelineMode {
  mode: 'single' | 'multi';
}

export interface EventsTimelineProps {
  events: TimelineEvent[];
  mode: 'single' | 'multi';
  /** Single mode: the day to render (defaults to the first event's date). */
  day?: string;
  /** When provided, each card becomes a clickable button that fires this with
   *  the event's `id` — used by the Events tab to open the detail slide-over. */
  onSelect?: (id: string) => void;
}

// ── calendar → timeline mapper (shared by Today + Events) ─────────────────

/** Default minutes a single calendar event occupies on the timeline. The
 * calendar feed carries no duration, so every event gets the same nominal slot
 * (lane-packing + the label-min clamp keep neighbours from colliding). */
export const DEFAULT_EVENT_DURATION_MIN = 30;

/** Normalize the feed's free-text impact to the timeline's 3-level scale. */
export function timelineImpact(impact: string): TimelineImpact {
  const i = (impact ?? '').trim().toLowerCase();
  if (i === 'high') return 'high';
  if (i === 'medium' || i === 'med') return 'medium';
  return 'low';
}

/** The "HH:MM" a calendar row sits at: local time of its resolved instant when
 * known, else the feed's wall-clock `event_time`, else midnight. */
export function eventClock(e: FxEconomicCalendarRow): string {
  const inst = eventInstant(e);
  if (inst) {
    const hh = String(inst.getHours()).padStart(2, '0');
    const mm = String(inst.getMinutes()).padStart(2, '0');
    return `${hh}:${mm}`;
  }
  const t = (e.event_time ?? '').trim();
  if (/^\d{1,2}:\d{2}/.test(t)) {
    const [h, m] = t.split(':');
    return `${h.padStart(2, '0')}:${m.slice(0, 2)}`;
  }
  return '00:00';
}

/**
 * Map calendar rows to the reusable timeline's event shape. Shared by the Today
 * single-day timeline and the Events multi-day timeline so both views agree on
 * the local-day bucketing, clock, and impact normalization.
 */
export function eventsToTimeline(rows: FxEconomicCalendarRow[]): TimelineEvent[] {
  return rows.map((e) => ({
    id: String(e.id),
    date: eventLocalDateKey(e),
    time: eventClock(e),
    durationMin: DEFAULT_EVENT_DURATION_MIN,
    currency: e.country,
    title: e.event_name,
    impact: timelineImpact(e.impact),
  }));
}

// ── layout constants (px) ────────────────────────────────────────────────
export const TL_SCALES = { hour: 64, day: 22 } as const; // px per hour
export const TL_WIN_START = 0;
export const TL_WIN_END = 24; // daily window 00:00 → 24:00
export const TL_LANE_H = 46;
export const TL_LANE_GAP = 9;
export const TL_BODY_PAD = 10;
/** Minimum rendered card width so the label/time always fit. Widened from 88 so
 * short-duration cards show more of the title before the ellipsis truncation
 * kicks in; lane-packing runs on this rendered width so the wider boxes still
 * never share a lane with a near neighbour. */
export const TL_LABEL_MIN = 130;
/** Floor on the single-mode canvas width before it scrolls on narrow screens. */
export const TL_FIT_MIN_W = 720;

const HOURS = TL_WIN_END - TL_WIN_START;

// ── pure helpers (unit-tested directly) ──────────────────────────────────

export function minsOfDay(time: string): number {
  const [h, m] = time.split(':').map(Number);
  return (h || 0) * 60 + (m || 0);
}

export interface LaneItem {
  startMin: number;
  endMin: number; // RENDERED end (start + max(duration, labelMin) in minutes)
  lane: number;
}

/**
 * Greedy lane packing: each item lands in the first lane whose last card ends
 * at or before this card's start. `endMin` must be the *rendered* end (derived
 * from the clamped width) so visually-overlapping boxes never share a lane.
 * Mutates each item's `lane` in place; returns the lane count.
 */
export function packLanes(items: LaneItem[]): number {
  const laneEnds: number[] = [];
  for (const it of items) {
    let lane = laneEnds.findIndex((end) => end <= it.startMin);
    if (lane === -1) {
      lane = laneEnds.length;
      laneEnds.push(0);
    }
    laneEnds[lane] = it.endMin;
    it.lane = lane;
  }
  return laneEnds.length || 1;
}

export interface PositionedCard {
  event: TimelineEvent;
  startMin: number;
  x: number;
  width: number;
  lane: number;
}

/**
 * Position one day's events. Width is clamped to `TL_LABEL_MIN`; lane-packing
 * runs on the rendered width converted back to minutes (the bug fix).
 */
export function layoutDay(events: TimelineEvent[], pxPerHour: number): PositionedCard[] {
  const minPerPx = 60 / pxPerHour;
  const sorted = [...events].sort((a, b) => minsOfDay(a.time) - minsOfDay(b.time));

  const cards: (PositionedCard & LaneItem)[] = sorted.map((event) => {
    const startMin = minsOfDay(event.time);
    const width = Math.max(TL_LABEL_MIN, (event.durationMin / 60) * pxPerHour);
    const renderedEndMin = startMin + width * minPerPx;
    return {
      event,
      startMin,
      x: (startMin / 60) * pxPerHour,
      width,
      lane: -1,
      endMin: renderedEndMin,
    };
  });

  packLanes(cards);
  return cards.map(({ event, startMin, x, width, lane }) => ({ event, startMin, x, width, lane }));
}

export function impactClass(impact: TimelineImpact): string {
  if (impact === 'high') return 'impact-high';
  if (impact === 'medium') return 'impact-med';
  return 'impact-low';
}

/** Tailwind classes for a card's accent (left border) + tint, by impact. */
function impactStyle(impact: TimelineImpact): string {
  if (impact === 'high') return 'border-l-down bg-down/[0.13]';
  if (impact === 'medium') return 'border-l-warn bg-warn/[0.13]';
  return 'border-l-ink-mute bg-white/[0.045]';
}

function shortDayLabel(date: string): string {
  const d = new Date(`${date}T00:00:00Z`);
  return d
    .toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', timeZone: 'UTC' })
    .replace(',', ' ·');
}

function distinctDays(events: TimelineEvent[], fallback?: string): string[] {
  const days = [...new Set(events.map((e) => e.date))].sort();
  if (days.length > 0) return days;
  return fallback ? [fallback] : [];
}

// ── component ─────────────────────────────────────────────────────────────

export default function EventsTimeline({ events, mode, day, onSelect }: EventsTimelineProps) {
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const [measuredW, setMeasuredW] = useState(0);
  const [scale, setScale] = useState<'hour' | 'day'>('hour');

  useLayoutEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const update = () => setMeasuredW(el.clientWidth);
    update();
    if (typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const days =
    mode === 'single'
      ? distinctDays(
          events.filter((e) => !day || e.date === day),
          day ?? events[0]?.date,
        )
      : distinctDays(events);

  const dayCount = Math.max(days.length, 1);

  // px/hour: single mode fits the whole window to the mount width (floored so it
  // scrolls on narrow screens); multi mode uses the chosen scale.
  let pxPerHour: number;
  if (mode === 'single') {
    const avail = Math.max(measuredW, TL_FIT_MIN_W);
    pxPerHour = avail / (HOURS * dayCount);
  } else {
    pxPerHour = TL_SCALES[scale];
  }
  const tickStep = mode === 'multi' && scale === 'day' ? 3 : mode === 'single' ? 2 : 1;
  const showDayLabel = mode === 'multi';

  const dayWidth = HOURS * pxPerHour;
  const totalW = dayWidth * dayCount;

  const byDay: Record<string, TimelineEvent[]> = {};
  for (const e of events) (byDay[e.date] = byDay[e.date] || []).push(e);

  const dayLayouts = days.map((d) => layoutDay(byDay[d] || [], pxPerHour));
  const maxLanes = Math.max(1, ...dayLayouts.map((cards) => Math.max(0, ...cards.map((c) => c.lane + 1))));
  const bodyH = TL_BODY_PAD * 2 + maxLanes * TL_LANE_H + (maxLanes - 1) * TL_LANE_GAP;

  const ticks: number[] = [];
  for (let h = TL_WIN_START; h <= TL_WIN_END; h += tickStep) ticks.push(h);

  return (
    <div className="flex flex-col gap-3">
      {mode === 'multi' ? (
        <div className="flex flex-wrap items-center gap-2.5">
          <span className="text-[11px] uppercase tracking-[0.08em] text-ink-mute">Scale</span>
          <div className="inline-flex overflow-hidden rounded-md border border-white/10 text-[11px]">
            {(['day', 'hour'] as const).map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => setScale(s)}
                aria-pressed={scale === s}
                className={`px-2.5 py-1 capitalize transition-colors ${
                  scale === s ? 'bg-accent/20 text-accent' : 'text-ink-mute hover:text-ink-soft'
                }`}
              >
                {s}
              </button>
            ))}
          </div>
          <span className="ml-auto inline-flex flex-wrap gap-3 text-[11px] text-ink-mute" aria-hidden>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-down" /> High
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-warn" /> Medium
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-ink-mute" /> Low
            </span>
          </span>
        </div>
      ) : null}

      <div
        ref={scrollRef}
        className={`tl-scroll max-w-full overflow-y-hidden rounded-[10px] border border-white/10 bg-surface ${
          mode === 'single' ? 'overflow-x-hidden max-[760px]:overflow-x-auto' : 'overflow-x-auto'
        }`}
      >
        <div className="relative" style={{ width: totalW }}>
          {/* axis */}
          <div
            className="sticky top-0 z-[3] flex h-[42px] border-b border-white/10 bg-surface"
            style={{ width: totalW }}
          >
            {days.map((d) => (
              <div key={d} className="relative flex-none border-r border-white/[0.06] last:border-r-0" style={{ width: dayWidth }}>
                {showDayLabel ? (
                  <span className="absolute left-0 top-[5px] whitespace-nowrap px-2.5 text-[11px] font-semibold uppercase tracking-[0.06em] text-ink-soft">
                    {shortDayLabel(d)}
                  </span>
                ) : null}
                {ticks.map((h) => {
                  const x = (h - TL_WIN_START) * pxPerHour;
                  return (
                    <span key={`t-${h}`}>
                      <span className="absolute bottom-0 top-[22px] w-0 border-l border-white/10" style={{ left: x }} />
                      {h < TL_WIN_END ? (
                        <span
                          className="absolute bottom-[4px] -translate-x-1/2 whitespace-nowrap font-mono text-[9.5px] text-ink-mute"
                          style={{ left: x }}
                        >
                          {String(h).padStart(2, '0')}:00
                        </span>
                      ) : null}
                    </span>
                  );
                })}
              </div>
            ))}
          </div>

          {/* body */}
          <div className="relative" style={{ width: totalW, height: bodyH }}>
            {days.map((d, di) => {
              const dayLeft = di * dayWidth;
              return (
                <span key={`col-${d}`}>
                  <div
                    className="absolute bottom-0 top-0 border-r border-white/[0.06]"
                    style={{ left: dayLeft, width: dayWidth }}
                  />
                  {ticks.map((h) => (
                    <span
                      key={`g-${d}-${h}`}
                      className="tl-grid absolute bottom-0 top-0 w-0 border-l border-white/10"
                      style={{ left: dayLeft + (h - TL_WIN_START) * pxPerHour }}
                    />
                  ))}
                </span>
              );
            })}

            {dayLayouts.map((cards, di) => {
              const dayLeft = di * dayWidth;
              return cards.map((c, ci) => {
                const top = TL_BODY_PAD + c.lane * (TL_LANE_H + TL_LANE_GAP);
                const e = c.event;
                const clickable = Boolean(onSelect && e.id != null);
                const className = `tl-card absolute box-border overflow-hidden rounded-md border-l-[3px] px-[7px] py-[5px] text-left ${
                  clickable ? 'cursor-pointer transition-shadow hover:ring-1 hover:ring-inset hover:ring-white/20' : ''
                } ${impactClass(e.impact)} ${impactStyle(e.impact)}`;
                const style = { left: dayLeft + c.x, top, width: c.width, height: TL_LANE_H };
                const title = `${e.time} ${e.currency} — ${e.title} (${e.durationMin} min)`;
                const inner = (
                  <>
                    <span className="font-mono text-[10px] text-ink-mute">{e.time}</span>
                    <span className="ml-1.5 font-mono text-[11px] font-semibold text-ink-soft">{e.currency}</span>
                    <span className="mt-px block overflow-hidden text-ellipsis whitespace-nowrap text-[11.5px] leading-[1.25] text-ink-soft">
                      {e.title}
                    </span>
                  </>
                );
                const key = e.id ?? `${e.date}-${e.time}-${ci}`;
                return clickable ? (
                  <button
                    key={key}
                    type="button"
                    onClick={() => onSelect!(e.id!)}
                    className={className}
                    style={style}
                    title={title}
                  >
                    {inner}
                  </button>
                ) : (
                  <div key={key} className={className} style={style} title={title}>
                    {inner}
                  </div>
                );
              });
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
