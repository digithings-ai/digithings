'use client';

import { useMemo } from 'react';
import Link from 'next/link';
import type { DashboardPositionEvent } from '@/lib/types';

export default function HoldingsActivityTable({ events }: { events: DashboardPositionEvent[] }) {
  const activity = useMemo(
    () =>
      events
        .filter((event) => event.event !== 'HOLD')
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
          opens · adds · trims · exits
        </span>
      </div>
      {activity.length ? (
        <div data-region="holdings-activity-scroll" className="min-h-0 flex-1 overflow-auto">
          <table className="w-full table-fixed border-collapse font-mono text-[0.78rem] [font-variant-numeric:tabular-nums]">
            <thead className="sticky top-0 z-10 bg-surface">
              <tr className="border-b border-hair text-[0.58rem] uppercase tracking-[0.1em] text-ink-mute">
                <th className="w-[31%] px-2 py-2.5 text-left font-normal sm:px-4 md:w-auto">Date</th>
                <th className="w-[20%] px-2 py-2.5 text-left font-normal sm:px-3 md:w-auto">Ticker</th>
                <th className="w-[24%] px-2 py-2.5 text-left font-normal sm:px-3 md:w-auto">Action</th>
                <th className="hidden px-3 py-2.5 text-right font-normal lg:table-cell">Weight</th>
                <th className="w-[25%] px-2 py-2.5 text-right font-normal sm:px-3 md:w-auto">Change</th>
                <th className="hidden px-4 py-2.5 text-right font-normal xl:table-cell">Price</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-hair">
              {activity.map((event) => (
                <tr key={`${event.date}-${event.ticker}-${event.event}`}>
                  <td className="px-2 py-2.5 text-ink-mute sm:px-4">{event.date}</td>
                  <td className="px-2 py-2.5 sm:px-3">
                    <Link
                      href={`/portfolio/tickers?ticker=${encodeURIComponent(event.ticker.toUpperCase())}`}
                      className="font-semibold text-ink hover:text-accent hover:underline"
                    >
                      {event.ticker}
                    </Link>
                  </td>
                  <td className="px-2 py-2.5 text-ink-soft sm:px-3">{event.event}</td>
                  <td className="hidden px-3 py-2.5 text-right text-ink lg:table-cell">
                    {event.weight_pct != null ? `${event.weight_pct.toFixed(1)}%` : '—'}
                  </td>
                  <td className="px-2 py-2.5 text-right text-ink-soft sm:px-3">
                    {event.weight_change_pct != null
                      ? `${event.weight_change_pct > 0 ? '+' : ''}${event.weight_change_pct.toFixed(1)}pp`
                      : '—'}
                  </td>
                  <td className="hidden px-4 py-2.5 text-right text-ink-soft xl:table-cell">
                    {event.price != null ? `$${event.price.toFixed(2)}` : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="px-6 py-10 text-center text-sm text-ink-mute">No position changes recorded.</p>
      )}
    </section>
  );
}