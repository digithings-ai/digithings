'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import { usePathname, useSearchParams } from 'next/navigation';
import { CalendarClock, ChevronRight, FileText, Globe, Users } from 'lucide-react';
import { briefHref } from './BriefPanel';
import type {
  FxEconomicCalendarRow,
  FxEventCitation,
  FxEventSnapshotRow,
} from '@/lib/twelve-x/types';

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

interface MatchedOpinions {
  mentions: number;
  brokers: string[];
  citations: FxEventCitation[];
  eventKey: string;
}

function ExpandedOpinions({
  opinions,
  runDate,
}: {
  opinions: MatchedOpinions;
  runDate: string | null;
}) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  return (
    <div className="space-y-2 border-t border-border-subtle/60 px-4 py-3">
      {opinions.citations.length > 0 ? (
        opinions.citations.map((c, i) => (
          <div key={`${c.broker}-${c.source_file}-${i}`} className="rounded-lg bg-white/[0.02] p-3">
            <div className="mb-1 flex items-center justify-between gap-2">
              <span className="font-mono text-xs font-semibold text-text-primary">
                {c.broker || 'Unknown desk'}
              </span>
              {c.source_file ? (
                <Link
                  href={briefHref(
                    pathname,
                    new URLSearchParams(searchParams.toString()),
                    c.source_file,
                    runDate
                  )}
                  scroll={false}
                  className="flex shrink-0 items-center gap-1 text-[11px] font-medium text-fin-blue hover:underline"
                  title={`Open brief ${c.source_file}`}
                >
                  <FileText size={11} aria-hidden />
                  Brief
                </Link>
              ) : null}
            </div>
            {c.expected_outcome ? (
              <p className="text-xs leading-snug text-text-secondary">
                <span className="text-text-muted">Expected: </span>
                {c.expected_outcome}
              </p>
            ) : null}
            {c.fx_impact ? (
              <p className="mt-1 text-xs leading-snug text-text-secondary">
                <span className="text-text-muted">FX impact: </span>
                {c.fx_impact}
              </p>
            ) : null}
          </div>
        ))
      ) : (
        <p className="text-xs text-text-muted">
          {opinions.brokers.length > 0
            ? `Cited by ${opinions.brokers.join(', ')}.`
            : 'No broker detail available.'}
        </p>
      )}
    </div>
  );
}

function EventRow({
  event,
  opinions,
  runDate,
}: {
  event: FxEconomicCalendarRow;
  opinions: MatchedOpinions | null;
  runDate: string | null;
}) {
  const [open, setOpen] = useState(false);
  const { text: impactText, dot: impactDot } = impactClass(event.impact);
  const time = formatLocalTime(event.event_datetime_utc) ?? event.event_time ?? null;
  const hasOpinions = Boolean(opinions && opinions.mentions > 0);

  return (
    <div className="overflow-hidden">
      <button
        type="button"
        // A row with no broker opinions has nothing to expand: disable it so it is
        // neither keyboard-focusable nor an interactive no-op. Rows WITH opinions
        // stay the expand/collapse toggle.
        disabled={!hasOpinions}
        onClick={hasOpinions ? () => setOpen((v) => !v) : undefined}
        className={`flex w-full items-center gap-3 px-4 py-3 text-left transition-colors ${
          hasOpinions ? 'cursor-pointer hover:bg-white/[0.02]' : 'cursor-default'
        }`}
        aria-expanded={hasOpinions ? open : undefined}
      >
        {/* Time column */}
        <div className="w-14 shrink-0 text-right">
          <span className="qn-metric block tabular-nums text-sm text-text-primary">
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

        {/* Forecast / actual */}
        <div className="hidden w-40 shrink-0 items-center justify-end gap-3 text-right sm:flex">
          {event.forecast ? (
            <span className="text-[11px] text-text-muted">
              Fcst <span className="tabular-nums text-text-secondary">{event.forecast}</span>
            </span>
          ) : null}
          {event.actual ? (
            <span className="text-[11px] text-text-muted">
              Act <span className="tabular-nums text-text-primary">{event.actual}</span>
            </span>
          ) : null}
        </div>

        {/* Opinions affordance */}
        <div className="flex w-24 shrink-0 items-center justify-end gap-1.5">
          {hasOpinions ? (
            <>
              <span className="flex items-center gap-1 text-[11px] text-text-muted">
                <Users size={12} aria-hidden />
                <span className="tabular-nums text-text-secondary">{opinions!.mentions}</span>
              </span>
              <ChevronRight
                size={14}
                aria-hidden
                className={`text-text-muted transition-transform ${open ? 'rotate-90' : ''}`}
              />
            </>
          ) : null}
        </div>
      </button>

      {hasOpinions && open ? (
        <ExpandedOpinions opinions={opinions!} runDate={runDate} />
      ) : null}
    </div>
  );
}

export default function EventsTab({
  events,
  opinions,
  runDate,
}: {
  events: FxEconomicCalendarRow[];
  opinions: FxEventSnapshotRow[];
  runDate: string | null;
}) {
  // Index broker opinions so each upcoming calendar row can pick up the aggregated
  // desk views. Two lookups, mirroring how twelve-x groups risk events:
  //   1. byExternalId — keyed on the snapshot's `calendar_external_id` (== the calendar
  //      row's `external_id`) for calendar-linked snapshots. This is the precise join
  //      and is preferred whenever available.
  //   2. byNameAndDate — keyed on (normalizedName + '\u001f' + event_date) for unlinked
  //      snapshots. Including the date is what stops same-named events ("CPI",
  //      "Rate Decision") on different dates/countries from colliding. Name alone is
  //      never used as a key.
  const { byExternalId, byNameAndDate } = useMemo(() => {
    const nameDateKey = (name: string, date: string | null): string =>
      `${normalizeName(name)}\u001f${date ?? ''}`;
    const externalIdMap = new Map<string, MatchedOpinions>();
    const nameDateMap = new Map<string, MatchedOpinions>();
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
      // Unlinked snapshot: fall back to (name + date). A normalized name is required
      // for a usable key, and first write wins to keep matching deterministic.
      const n = normalizeName(o.event_name);
      if (!n) continue;
      const key = nameDateKey(o.event_name, o.event_date);
      if (!nameDateMap.has(key)) nameDateMap.set(key, matched);
    }
    return { byExternalId: externalIdMap, byNameAndDate: nameDateMap };
  }, [opinions]);

  const matchOpinions = (event: FxEconomicCalendarRow): MatchedOpinions | null => {
    // Prefer the exact calendar_external_id ↔ external_id key match.
    const externalId = (event.external_id ?? '').trim();
    if (externalId) {
      const linked = byExternalId.get(externalId);
      if (linked) return linked;
    }
    // Fall back to (normalized event_name AND event_date) — never name alone.
    return byNameAndDate.get(`${normalizeName(event.event_name)}\u001f${event.event_date}`) ?? null;
  };

  // Group the upcoming window by day for a timeline layout.
  const grouped = useMemo(() => {
    const byDate = new Map<string, FxEconomicCalendarRow[]>();
    for (const e of events) {
      const list = byDate.get(e.event_date) ?? [];
      list.push(e);
      byDate.set(e.event_date, list);
    }
    return [...byDate.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [events]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3 px-1">
        <CalendarClock size={18} className="shrink-0 text-fin-blue" aria-hidden />
        <h2 className="text-base font-semibold text-text-primary md:text-lg">Upcoming catalysts</h2>
        {runDate ? (
          <span className="ml-auto font-mono text-[10px] text-text-muted">
            opinions as of {runDate}
          </span>
        ) : null}
      </div>

      <p className="max-w-2xl px-1 text-xs text-text-muted">
        The next 14 days of macro events (times in your local timezone). Rows with aggregated broker
        expectations are expandable — open to see which desks weighed in, what they expect, and the
        FX impact they flag.
      </p>

      {grouped.length > 0 ? (
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
                    runDate={runDate}
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
      )}
    </div>
  );
}
