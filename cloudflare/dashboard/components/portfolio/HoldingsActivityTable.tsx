'use client';

import { useMemo, useState, Fragment } from 'react';
import Link from 'next/link';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@digithings/web/ui';
import type { DashboardPositionEvent } from '@/lib/types';
import { isMaterialBookEvent } from '@/lib/brief-book-event';
import { thesisDetailHref, tickerDossierHref } from '@/lib/portfolio-url-state';
import { usablePmRationale } from '@/lib/pm-rationale';

function signedPct(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—';
  return `${value > 0 ? '+' : ''}${value.toFixed(2)}%`;
}

function money(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—';
  return `$${value.toFixed(2)}`;
}

function eventKey(event: DashboardPositionEvent, index: number): string {
  return event.id ?? `${event.date}-${event.ticker}-${event.event}-${index}`;
}

function EventDetail({ event }: { event: DashboardPositionEvent }) {
  const reason = usablePmRationale(event.reason);
  const isSell = event.event === 'TRIM' || event.event === 'EXIT';
  return (
    <TableRow data-testid="ledger-event-detail" className="border-0 bg-ink/[0.02] hover:bg-ink/[0.02]">
      <TableCell colSpan={7} className="border-t border-hair/70 px-3 py-3 sm:px-4 whitespace-normal">
        <div className="grid gap-3 text-[0.72rem] text-ink-soft sm:grid-cols-2">
          <dl className="m-0 grid grid-cols-[7.5rem_1fr] gap-x-3 gap-y-1.5 font-mono tabular-nums">
            <dt className="uppercase tracking-wider text-ink-mute">Avg entry</dt>
            <dd className="m-0 text-ink">{money(event.avg_entry_price)}</dd>
            <dt className="uppercase tracking-wider text-ink-mute">
              {isSell ? 'Exit / fill' : 'Fill'}
            </dt>
            <dd className="m-0 text-ink">{money(event.price)}</dd>
            {isSell ? (
              <>
                <dt className="uppercase tracking-wider text-ink-mute">Sold wt</dt>
                <dd className="m-0 text-ink">
                  {event.sold_weight_pct != null ? `${event.sold_weight_pct.toFixed(1)}%` : '—'}
                </dd>
                <dt className="uppercase tracking-wider text-ink-mute">Realized</dt>
                <dd
                  className={`m-0 ${
                    event.realized_return_pct == null
                      ? 'text-ink'
                      : event.realized_return_pct >= 0
                        ? 'text-up'
                        : 'text-down'
                  }`}
                >
                  {signedPct(event.realized_return_pct)}
                </dd>
              </>
            ) : null}
            <dt className="uppercase tracking-wider text-ink-mute">Residual wt</dt>
            <dd className="m-0 text-ink">
              {event.weight_pct != null ? `${event.weight_pct.toFixed(1)}%` : '—'}
            </dd>
            <dt className="uppercase tracking-wider text-ink-mute">Prior wt</dt>
            <dd className="m-0 text-ink">
              {event.prev_weight_pct != null ? `${event.prev_weight_pct.toFixed(1)}%` : '—'}
            </dd>
          </dl>
          <div className="space-y-2">
            {reason ? (
              <p className="m-0 leading-snug text-ink-soft">{reason}</p>
            ) : (
              <p className="m-0 text-ink-mute">No PM rationale on this fill.</p>
            )}
            <div className="flex flex-wrap gap-x-4 gap-y-1">
              <Link
                href={tickerDossierHref(event.ticker)}
                className="font-medium text-accent hover:underline"
              >
                Ticker dossier
              </Link>
              {event.thesis_id ? (
                <Link
                  href={thesisDetailHref(event.thesis_id)}
                  className="font-medium text-accent hover:underline"
                >
                  Thesis
                </Link>
              ) : null}
            </div>
          </div>
        </div>
      </TableCell>
    </TableRow>
  );
}

export default function HoldingsActivityTable({ events }: { events: DashboardPositionEvent[] }) {
  const [expandedKey, setExpandedKey] = useState<string | null>(null);
  const activity = useMemo(
    () =>
      events
        .filter((event) => isMaterialBookEvent(event))
        .slice()
        .sort((a, b) => b.date.localeCompare(a.date) || a.ticker.localeCompare(b.ticker)),
    [events]
  );

  return (
    <section
      data-region="holdings-activity"
      className="flex h-full min-h-0 flex-col border border-hair bg-surface"
    >
      <div className="flex items-center justify-between gap-3 border-b border-hair bg-term-bg px-4 py-3 md:px-6">
        <h3 className="font-display text-xl font-normal tracking-tight text-ink">Activity</h3>
        <span className="font-mono text-[0.62rem] uppercase tracking-wider text-ink-mute">
          opens · adds · trims · exits · tap row for detail
        </span>
      </div>
      {activity.length ? (
        <div data-region="holdings-activity-scroll" className="min-h-0 flex-1 overflow-auto [&>div]:overflow-visible">
          <Table className="table-fixed border-collapse font-mono text-[0.78rem] [font-variant-numeric:tabular-nums]">
            <TableHeader className="sticky top-0 z-10 bg-surface">
              <TableRow className="border-hair text-[0.58rem] uppercase tracking-[0.1em] text-ink-mute hover:bg-transparent">
                <TableHead className="h-auto w-[22%] px-2 py-2.5 font-normal sm:px-4 md:w-auto">Date</TableHead>
                <TableHead className="h-auto w-[14%] px-2 py-2.5 font-normal sm:px-3 md:w-auto">Ticker</TableHead>
                <TableHead className="h-auto w-[14%] px-2 py-2.5 font-normal sm:px-3 md:w-auto">Action</TableHead>
                <TableHead numeric className="h-auto w-[16%] px-2 py-2.5 font-normal sm:px-3 md:w-auto">Change</TableHead>
                <TableHead numeric className="h-auto hidden px-3 py-2.5 font-normal lg:table-cell">Entry</TableHead>
                <TableHead numeric className="h-auto hidden px-3 py-2.5 font-normal md:table-cell">Fill</TableHead>
                <TableHead numeric className="h-auto w-[18%] px-2 py-2.5 font-normal sm:px-3 md:w-auto">
                  Realized
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody className="divide-y divide-hair">
              {activity.map((event, index) => {
                const key = eventKey(event, index);
                const open = expandedKey === key;
                const isSell = event.event === 'TRIM' || event.event === 'EXIT';
                const realized = event.realized_return_pct;
                return (
                  <Fragment key={key}>
                    <TableRow
                      data-testid={`ledger-row-${event.ticker}-${event.date}`}
                      className={`cursor-pointer border-0 hover:bg-ink/[0.03] has-aria-expanded:bg-transparent ${open ? 'bg-ink/[0.02]' : ''}`}
                      onClick={() => setExpandedKey(open ? null : key)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault();
                          setExpandedKey(open ? null : key);
                        }
                      }}
                      tabIndex={0}
                      aria-expanded={open}
                    >
                      <TableCell className="px-2 py-2.5 text-ink-mute sm:px-4">{event.date}</TableCell>
                      <TableCell className="px-2 py-2.5 sm:px-3">
                        <Link
                          href={tickerDossierHref(event.ticker)}
                          className="font-semibold text-ink hover:text-accent hover:underline"
                          onClick={(e) => e.stopPropagation()}
                          onKeyDown={(e) => e.stopPropagation()}
                        >
                          {event.ticker}
                        </Link>
                      </TableCell>
                      <TableCell className="px-2 py-2.5 text-ink-soft sm:px-3">{event.event}</TableCell>
                      <TableCell numeric className="px-2 py-2.5 text-ink-soft sm:px-3">
                        {event.weight_change_pct != null
                          ? `${event.weight_change_pct > 0 ? '+' : ''}${event.weight_change_pct.toFixed(1)}pp`
                          : '—'}
                      </TableCell>
                      <TableCell numeric className="hidden px-3 py-2.5 text-ink-soft lg:table-cell">
                        {money(event.avg_entry_price)}
                      </TableCell>
                      <TableCell numeric className="hidden px-3 py-2.5 text-ink-soft md:table-cell">
                        {money(event.price)}
                      </TableCell>
                      <TableCell
                        numeric
                        className={`px-2 py-2.5 sm:px-3 ${
                          !isSell || realized == null
                            ? 'text-ink-mute'
                            : realized >= 0
                              ? 'text-up'
                              : 'text-down'
                        }`}
                      >
                        {isSell ? signedPct(realized) : '—'}
                      </TableCell>
                    </TableRow>
                    {open ? <EventDetail event={event} /> : null}
                  </Fragment>
                );
              })}
            </TableBody>
          </Table>
        </div>
      ) : (
        <p className="px-6 py-10 text-center text-sm text-ink-mute">No position changes recorded.</p>
      )}
    </section>
  );
}
