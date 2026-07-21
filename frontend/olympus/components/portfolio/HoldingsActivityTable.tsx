'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import { Pager } from '@digithings/web';
import type { DashboardPositionEvent } from '@/lib/types';

const PAGE_SIZE = 10;

export default function HoldingsActivityTable({ events }: { events: DashboardPositionEvent[] }) {
  const activity = useMemo(
    () =>
      events
        .filter((event) => event.event !== 'HOLD')
        .slice()
        .sort((a, b) => b.date.localeCompare(a.date) || a.ticker.localeCompare(b.ticker)),
    [events]
  );
  const [page, setPage] = useState(0);
  const pageCount = Math.max(1, Math.ceil(activity.length / PAGE_SIZE));
  const safePage = Math.min(page, pageCount - 1);
  const visible = activity.slice(safePage * PAGE_SIZE, (safePage + 1) * PAGE_SIZE);

  return (
    <section data-region="holdings-activity" className="border border-hair bg-surface">
      <div className="flex items-center justify-between gap-3 border-b border-hair bg-term-bg px-4 py-3 md:px-6">
        <h3 className="font-display text-xl font-normal tracking-normal text-ink">Activity</h3>
        <span className="font-mono text-xs uppercase tracking-normal text-ink-mute">
          opens · adds · trims · exits
        </span>
      </div>
      {visible.length ? (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[620px] border-collapse font-mono text-xs [font-variant-numeric:tabular-nums]">
            <thead>
              <tr className="border-b border-hair text-xs uppercase tracking-normal text-ink-mute">
                <th className="px-4 py-2.5 text-left font-normal">Date</th>
                <th className="px-3 py-2.5 text-left font-normal">Ticker</th>
                <th className="px-3 py-2.5 text-left font-normal">Action</th>
                <th className="px-3 py-2.5 text-right font-normal">Weight</th>
                <th className="px-3 py-2.5 text-right font-normal">Change</th>
                <th className="px-4 py-2.5 text-right font-normal">Price</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-hair">
              {visible.map((event) => (
                <tr key={`${event.date}-${event.ticker}-${event.event}`}>
                  <td className="px-4 py-2.5 text-ink-mute">{event.date}</td>
                  <td className="px-3 py-2.5">
                    <Link
                      href={`/portfolio/tickers?ticker=${encodeURIComponent(event.ticker.toUpperCase())}`}
                      className="font-semibold text-ink hover:text-accent hover:underline"
                    >
                      {event.ticker}
                    </Link>
                  </td>
                  <td className="px-3 py-2.5 text-ink-soft">{event.event}</td>
                  <td className="px-3 py-2.5 text-right text-ink">
                    {event.weight_pct != null ? `${event.weight_pct.toFixed(1)}%` : '—'}
                  </td>
                  <td className="px-3 py-2.5 text-right text-ink-soft">
                    {event.weight_change_pct != null
                      ? `${event.weight_change_pct > 0 ? '+' : ''}${event.weight_change_pct.toFixed(1)}pp`
                      : '—'}
                  </td>
                  <td className="px-4 py-2.5 text-right text-ink-soft">
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
      {pageCount > 1 ? (
        <div className="flex justify-center border-t border-hair px-4 py-3">
          <Pager
            dress="capsule"
            onPrev={() => setPage(Math.max(0, safePage - 1))}
            onNext={() => setPage(Math.min(pageCount - 1, safePage + 1))}
            prevDisabled={safePage === 0}
            nextDisabled={safePage === pageCount - 1}
            prevAriaLabel="Newer activity"
            nextAriaLabel="Older activity"
          >
            <span className="px-3 font-mono text-xs text-ink-mute">
              {safePage + 1} / {pageCount}
            </span>
          </Pager>
        </div>
      ) : null}
    </section>
  );
}
