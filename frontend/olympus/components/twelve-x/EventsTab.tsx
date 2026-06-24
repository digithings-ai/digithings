'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { CalendarClock, ChevronRight, Globe, Users } from 'lucide-react';
import { eventLocalDateKey, hasResolvedTime } from '@/lib/twelve-x/fetch';
import type {
  FxEconomicCalendarRow,
  FxEventCitation,
  FxEventSnapshotRow,
} from '@/lib/twelve-x/types';
import EventsTimeline, { eventsToTimeline } from './EventsTimeline';
import EventDetailPanel from './EventDetailPanel';

/** The two Events views; List is the default. */
type EventsView = 'list' | 'timeline';
const VIEWS: { key: EventsView; label: string }[] = [
  { key: 'list', label: 'List' },
  { key: 'timeline', label: 'Timeline' },
];

/** Impact → .fin-* color + dot styling. */
function impactClass(impact: string): { text: string; dot: string } {
  const i = impact.trim().toLowerCase();
  if (i === 'high') return { text: 'text-fin-red', dot: 'bg-fin-red' };
  if (i === 'medium') return { text: 'text-fin-amber', dot: 'bg-fin-amber' };
  return { text: 'text-text-muted', dot: 'bg-text-muted/60' };
}

function impactLabel(impact: string): string {
  const i = impact.trim();
  if (!i) return '—';
  return i.charAt(0).toUpperCase() + i.slice(1).toLowerCase();
}

/** Format an ISO timestamptz to the viewer's locale time, or null when absent. */
function formatLocalTime(iso: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
}

/** Format an ISO date (YYYY-MM-DD) to a short, locale-aware day label. */
function formatDateLabel(isoDate: string): string {
  // Treat the bare date as local midnight for a stable, tz-neutral day label.
  const d = new Date(`${isoDate}T00:00:00`);
  if (Number.isNaN(d.getTime())) return isoDate;
  return d.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' });
}

function asStringList(raw: unknown): string[] {
  if (Array.isArray(raw)) return raw.map((x) => String(x)).filter((s) => s.trim().length > 0);
  return [];
}

function asCitations(raw: unknown): FxEventCitation[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((c): c is Record<string, unknown> => Boolean(c) && typeof c === 'object')
    .map((c) => ({
      broker: String(c.broker ?? ''),
      expected_outcome: String(c.expected_outcome ?? ''),
      fx_impact: String(c.fx_impact ?? ''),
      source_file: String(c.source_file ?? ''),
      brief_key: String(c.brief_key ?? ''),
    }));
}

/**
 * Loose normalization for matching a calendar event_name to a snapshot event_name.
 * Tolerates a null/undefined/non-string `name` (malformed row) → '' so a single
 * bad row can't crash the tab.
 */
function normalizeName(name: string | null | undefined): string {
  if (typeof name !== 'string') return '';
  return name
    .toLowerCase()
    .replace(/[^a-z0-9 ]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

// Snapshot event_names often carry a leading country/region code that the
// calendar event_name lacks ("US FOMC Statement" / "[CN] Retail Sales YoY" vs
// "FOMC Statement"). Split that prefix off so the name-fallback can align the
// two, qualified by country to avoid cross-country false matches.
const COUNTRY_CODES = new Set([
  'us', 'eu', 'ez', 'gb', 'uk', 'jp', 'cn', 'au', 'nz', 'ca', 'ch', 'de', 'fr',
  'it', 'es', 'se', 'no', 'dk', 'tr', 'sg', 'in', 'kr', 'mx', 'za', 'br', 'hk',
  'tw', 'id', 'th', 'pl', 'cz', 'hu', 'il',
]);

function splitCountry(normalized: string): { country: string; rest: string } {
  const sp = normalized.indexOf(' ');
  if (sp <= 0) return { country: '', rest: normalized };
  const head = normalized.slice(0, sp);
  if (COUNTRY_CODES.has(head)) return { country: head, rest: normalized.slice(sp + 1) };
  return { country: '', rest: normalized };
}

/**
 * Aggregated broker opinions matched to a single calendar event. Exported so the
 * EventDetailPanel slide-over can render the same desk-commentary shape that the
 * list/timeline produce via `matchOpinions`.
 */
export interface MatchedOpinions {
  mentions: number;
  brokers: string[];
  citations: FxEventCitation[];
  eventKey: string;
}

function EventRow({
  event,
  opinions,
  onSelect,
  highlight = false,
}: {
  event: FxEconomicCalendarRow;
  opinions: MatchedOpinions | null;
  onSelect: (event: FxEconomicCalendarRow) => void;
  highlight?: boolean;
}) {
  const rowRef = useRef<HTMLDivElement>(null);
  const { text: impactText, dot: impactDot } = impactClass(event.impact);
  // `resolvedTime` is true only when we have a real UTC instant to localize; a
  // falsy fallback to `event_time` is a raw venue/wall-clock string we mark with ≈.
  const resolvedTime = hasResolvedTime(event);
  const time = formatLocalTime(event.event_datetime_utc) ?? event.event_time ?? null;
  const hasOpinions = Boolean(opinions && opinions.mentions > 0);

  // When this row is the cross-link target (catalyst → Events), scroll it into
  // view so the trader lands on the right catalyst.
  useEffect(() => {
    if (highlight && rowRef.current) {
      rowRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [highlight]);

  return (
    <div
      ref={rowRef}
      className={`overflow-hidden transition-colors ${
        highlight ? 'bg-fin-blue/10 ring-1 ring-inset ring-fin-blue/40' : ''
      }`}
    >
      <button
        type="button"
        // Every row opens the event-detail slide-over so the list and the timeline
        // behave identically — one click, same popup, opinions or not.
        onClick={() => onSelect(event)}
        className="flex w-full cursor-pointer items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-white/[0.02]"
      >
        {/* Time column */}
        <div className="w-14 shrink-0 text-right">
          <span className="qn-metric block tabular-nums text-sm text-text-primary">
            {!resolvedTime && time ? (
              <span
                className="mr-0.5 text-text-muted/70"
                title="Venue-local time — could not convert to your timezone"
              >
                ≈
              </span>
            ) : null}
            {time ?? '—'}
          </span>
        </div>

        {/* Impact dot */}
        <span className={`h-2 w-2 shrink-0 rounded-full ${impactDot}`} aria-hidden />

        {/* Event detail */}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="flex items-center gap-1 font-mono text-[11px] uppercase text-text-muted">
              <Globe size={11} aria-hidden />
              {event.country}
            </span>
            <span className={`text-[11px] font-medium ${impactText}`}>
              {impactLabel(event.impact)}
            </span>
          </div>
          <p className="truncate text-sm text-text-primary">{event.event_name}</p>
        </div>

        {/* Prior / forecast / actual */}
        <div className="hidden w-52 shrink-0 items-center justify-end gap-3 text-right sm:flex">
          {event.prior != null && event.prior !== '' ? (
            <span className="text-[11px] text-text-muted">
              Prior <span className="tabular-nums text-text-secondary">{event.prior}</span>
            </span>
          ) : null}
          {event.forecast != null && event.forecast !== '' ? (
            <span className="text-[11px] text-text-muted">
              Fcst <span className="tabular-nums text-text-secondary">{event.forecast}</span>
            </span>
          ) : null}
          {event.actual != null && event.actual !== '' ? (
            <span className="text-[11px] text-text-muted">
              Act <span className="tabular-nums text-text-primary">{event.actual}</span>
            </span>
          ) : null}
        </div>

        {/* Opinions count + open-detail affordance */}
        <div className="flex w-24 shrink-0 items-center justify-end gap-1.5">
          {hasOpinions ? (
            <span className="flex items-center gap-1 text-[11px] text-text-muted">
              <Users size={12} aria-hidden />
              <span className="tabular-nums text-text-secondary">{opinions!.mentions}</span>
            </span>
          ) : null}
          <ChevronRight size={14} aria-hidden className="text-text-muted" />
        </div>
      </button>
    </div>
  );
}

export default function EventsTab({
  events,
  opinions,
  runDate,
  focus,
  initialView = 'list',
  initialSelectedId = null,
}: {
  events: FxEconomicCalendarRow[];
  opinions: FxEventSnapshotRow[];
  runDate: string | null;
  /** Cross-link target from another tab (catalyst → Events): scroll/highlight it. */
  focus?: { externalId?: string | null; name: string | null } | null;
  /** Seed the active view — defaults to List; the non-default views are set
   *  explicitly only for deterministic SSR rendering in tests. */
  initialView?: EventsView;
  /** Seed the open detail slide-over by event id — used so the open-panel state
   *  is renderable under renderToStaticMarkup in tests. */
  initialSelectedId?: string | null;
}) {
  // Index broker opinions so each upcoming calendar row can pick up the aggregated
  // desk views. Two lookups, mirroring how twelve-x groups risk events:
  //   1. byExternalId — keyed on the snapshot's `calendar_external_id` (== the calendar
  //      row's `external_id`) for calendar-linked snapshots. This is the precise join
  //      and is preferred whenever available.
  //   2. byNameAndDate — keyed on (normalizedName + date), with a country-stripped,
  //      country-qualified fallback so a snapshot name like "US FOMC Statement" still
  //      aligns to the calendar's "FOMC Statement". The date + country qualifier stop
  //      same-named events on different dates/countries from colliding. Name alone is
  //      never used as a key.
  const { byExternalId, byNameAndDate } = useMemo(() => {
    const externalIdMap = new Map<string, MatchedOpinions>();
    const nameDateMap = new Map<string, MatchedOpinions>();
    const put = (key: string, m: MatchedOpinions) => {
      if (!nameDateMap.has(key)) nameDateMap.set(key, m); // first write wins -> deterministic
    };
    for (const o of opinions) {
      const matched: MatchedOpinions = {
        mentions: Number(o.mentions ?? 0),
        brokers: asStringList(o.brokers),
        citations: asCitations(o.citations),
        eventKey: o.event_key,
      };
      const externalId = (o.calendar_external_id ?? '').trim();
      if (externalId) {
        // Calendar-linked snapshot: precise key join. First write wins.
        if (!externalIdMap.has(externalId)) externalIdMap.set(externalId, matched);
        continue;
      }
      // Unlinked snapshot: register under name+date keys. The snapshot name often
      // carries a leading country code ("US FOMC Statement") the calendar name lacks,
      // so register BOTH the exact normalized name AND the country-stripped form, the
      // latter qualified by country to avoid cross-country false matches.
      const full = normalizeName(o.event_name);
      if (!full) continue;
      const date = o.event_date ?? '';
      put(`${full}|${date}`, matched);
      const { country, rest } = splitCountry(full);
      if (country && rest) put(`${rest}|${date}|${country}`, matched);
    }
    return { byExternalId: externalIdMap, byNameAndDate: nameDateMap };
  }, [opinions]);

  const matchOpinions = (event: FxEconomicCalendarRow): MatchedOpinions | null => {
    // 1) Prefer the exact calendar_external_id -> external_id key match.
    const externalId = (event.external_id ?? '').trim();
    if (externalId) {
      const linked = byExternalId.get(externalId);
      if (linked) return linked;
    }
    const name = normalizeName(event.event_name);
    const date = event.event_date ?? '';
    // 2) Exact (normalized name + date) - matches snapshots without a country prefix.
    const exact = byNameAndDate.get(`${name}|${date}`);
    if (exact) return exact;
    // 3) Country-qualified (name + date + calendar country) - matches snapshots whose
    //    name carried a country prefix that is now stripped. Never name alone.
    const country = normalizeName(event.country);
    if (country) {
      const qualified = byNameAndDate.get(`${name}|${date}|${country}`);
      if (qualified) return qualified;
    }
    return null;
  };

  // Group the upcoming window by day. Bucket by the LOCAL date of each event's
  // release instant (when known) so the day header agrees with the locale-
  // converted times shown in each row; fall back to the wall-clock feed date
  // only when there is no resolved instant.
  const grouped = useMemo(() => {
    const byDate = new Map<string, FxEconomicCalendarRow[]>();
    for (const e of events) {
      const key = eventLocalDateKey(e);
      const list = byDate.get(key) ?? [];
      list.push(e);
      byDate.set(key, list);
    }
    return [...byDate.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [events]);

  // Resolve the cross-link focus target to a concrete event id (by external_id,
  // then by normalized name) so the matching row can scroll/highlight itself.
  const focusedId = useMemo(() => {
    if (!focus) return null;
    const wantId = (focus.externalId ?? '').trim();
    if (wantId) {
      const byId = events.find((e) => (e.external_id ?? '').trim() === wantId);
      if (byId) return byId.id;
    }
    const wantName = normalizeName(focus.name ?? '');
    if (wantName) {
      const byName = events.find((e) => normalizeName(e.event_name) === wantName);
      if (byName) return byName.id;
    }
    return null;
  }, [focus, events]);

  // Active view (List default).
  const [view, setView] = useState<EventsView>(initialView);

  // The event whose detail slide-over is open, or null. Opened from both the List
  // and the Timeline so the two views surface the identical event-detail popup.
  // Seeded from initialSelectedId so the open state is renderable under SSR tests.
  const [selected, setSelected] = useState<FxEconomicCalendarRow | null>(
    () => events.find((e) => String(e.id) === initialSelectedId) ?? null,
  );

  // Map the full upcoming window to the reusable timeline's event shape, shared
  // with the Today single-day timeline (same local-day/clock/impact rules).
  const timelineEvents = useMemo(() => eventsToTimeline(events), [events]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3 px-1">
        <CalendarClock size={18} className="shrink-0 text-fin-blue" aria-hidden />
        <h2 className="text-base font-semibold text-text-primary md:text-lg">Upcoming catalysts</h2>
        {/* List | Timeline segmented control (demo's #evtSubnav). */}
        <div
          className="ml-auto inline-flex overflow-hidden rounded-md border border-white/10 text-[11px]"
          role="group"
          aria-label="Events view"
        >
          {VIEWS.map((v) => {
            const active = view === v.key;
            return (
              <button
                key={v.key}
                type="button"
                data-evtview={v.key}
                aria-pressed={active}
                onClick={() => setView(v.key)}
                className={`px-3 py-1 transition-colors ${
                  active ? 'bg-fin-blue/20 text-fin-blue' : 'text-text-muted hover:text-text-secondary'
                }`}
              >
                {v.label}
              </button>
            );
          })}
        </div>
        {runDate ? (
          <span className="font-mono text-[10px] text-text-muted">opinions as of {runDate}</span>
        ) : null}
      </div>

      <p className="max-w-2xl px-1 text-xs text-text-muted">
        The next 14 days of macro events — times in your local timezone where a precise release
        instant is known; <span className="text-text-muted/70">≈</span> marks venue-local times we
        could not convert. Open any event — in the list or on the timeline — to see which desks
        weighed in, what they expect, and the FX impact they flag.
      </p>

      {view === 'list' ? (
        grouped.length > 0 ? (
          <div className="space-y-4">
            {grouped.map(([dateStr, rows]) => (
              <div key={dateStr} className="glass-card overflow-hidden p-0">
                <div className="flex items-center gap-3 border-b border-border-subtle bg-bg-secondary px-4 py-2.5">
                  <h3 className="text-xs font-semibold uppercase tracking-wider text-text-secondary">
                    {formatDateLabel(dateStr)}
                  </h3>
                  <span className="ml-auto font-mono text-[10px] text-text-muted">{dateStr}</span>
                </div>
                <div className="divide-y divide-border-subtle">
                  {rows.map((event) => (
                    <EventRow
                      key={event.id}
                      event={event}
                      opinions={matchOpinions(event)}
                      onSelect={setSelected}
                      highlight={event.id === focusedId}
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="glass-card p-10 text-center text-sm text-text-muted">
            No upcoming economic events in the next 14 days.
          </div>
        )
      ) : null}

      {view === 'timeline' ? (
        <div className="glass-card p-4">
          {timelineEvents.length > 0 ? (
            <EventsTimeline
              events={timelineEvents}
              mode="multi"
              onSelect={(id) => setSelected(events.find((e) => String(e.id) === id) ?? null)}
            />
          ) : (
            <p className="text-sm text-text-muted">No upcoming economic events in the next 14 days.</p>
          )}
        </div>
      ) : null}

      <EventDetailPanel
        event={selected}
        opinions={selected ? matchOpinions(selected) : null}
        onClose={() => setSelected(null)}
      />
    </div>
  );
}
