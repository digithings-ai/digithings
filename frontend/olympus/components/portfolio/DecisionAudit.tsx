'use client';

import { useDeferredValue, useMemo, useState } from 'react';
import { ChevronLeft, ChevronRight, Search, X } from 'lucide-react';
import type { TableRow } from '@/lib/database.types';
import { directionAdjustedAlpha } from '@/lib/decision-scorecard';
import { fmtPct, signColorClass } from '@/components/observability/shared';

const PAGE_SIZE = 25;

export default function DecisionAudit({
  decisions,
}: {
  decisions: TableRow<'decision_log'>[];
}) {
  const [query, setQuery] = useState('');
  const [stance, setStance] = useState('all');
  const [status, setStatus] = useState('all');
  const [page, setPage] = useState(0);
  const deferredQuery = useDeferredValue(query.trim().toLowerCase());

  const stances = useMemo(
    () => [...new Set(decisions.map((decision) => decision.stance?.trim().toLowerCase()).filter(Boolean))].sort(),
    [decisions]
  );
  const filtered = useMemo(() => {
    return [...decisions]
      .filter((decision) => {
        const matchesQuery = !deferredQuery || [
          decision.ticker,
          decision.thesis,
          decision.reflection,
        ].some((value) => value?.toLowerCase().includes(deferredQuery));
        const matchesStance = stance === 'all' || decision.stance?.toLowerCase() === stance;
        const matchesStatus = status === 'all' || decision.status === status;
        return matchesQuery && matchesStance && matchesStatus;
      })
      .sort((a, b) => (b.run_date ?? '').localeCompare(a.run_date ?? ''));
  }, [decisions, deferredQuery, stance, status]);

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const activePage = Math.min(page, pageCount - 1);
  const pageRows = filtered.slice(activePage * PAGE_SIZE, (activePage + 1) * PAGE_SIZE);
  const first = filtered.length ? activePage * PAGE_SIZE + 1 : 0;
  const last = Math.min((activePage + 1) * PAGE_SIZE, filtered.length);

  const resetPage = () => setPage(0);

  return (
    <section className="border-y border-hair" aria-labelledby="decision-audit-heading">
      <div className="flex flex-col gap-4 border-b border-hair px-4 py-5 lg:flex-row lg:items-end lg:justify-between">
        <div className="space-y-1">
          <p className="font-mono text-[11px] uppercase text-ink-mute">Complete record</p>
          <h2 id="decision-audit-heading" className="text-sm font-semibold text-ink">
            Decision audit
          </h2>
          <p className="text-xs text-ink-mute">{filtered.length} matching observations · raw outcomes preserved</p>
        </div>

        <div className="grid gap-2 sm:grid-cols-[minmax(13rem,1fr)_auto_auto]">
          <label className="relative min-w-0">
            <span className="sr-only">Search decisions</span>
            <Search className="pointer-events-none absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-ink-mute" aria-hidden="true" />
            <input
              type="search"
              value={query}
              onChange={(event) => {
                setQuery(event.target.value);
                resetPage();
              }}
              placeholder="Search decisions"
              className="h-9 w-full border border-hair bg-transparent pl-9 pr-8 text-xs text-ink outline-none transition-colors placeholder:text-ink-mute focus:border-accent"
            />
            {query ? (
              <button
                type="button"
                onClick={() => {
                  setQuery('');
                  resetPage();
                }}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-ink-mute hover:text-ink"
                aria-label="Clear decision search"
                title="Clear search"
              >
                <X className="size-3.5" aria-hidden="true" />
              </button>
            ) : null}
          </label>

          <label>
            <span className="sr-only">Filter by stance</span>
            <select
              value={stance}
              onChange={(event) => {
                setStance(event.target.value);
                resetPage();
              }}
              aria-label="Filter by stance"
              className="h-9 border border-hair bg-surface px-3 text-xs capitalize text-ink outline-none focus:border-accent"
            >
              <option value="all">All stances</option>
              {stances.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
          </label>

          <label>
            <span className="sr-only">Filter by status</span>
            <select
              value={status}
              onChange={(event) => {
                setStatus(event.target.value);
                resetPage();
              }}
              aria-label="Filter by status"
              className="h-9 border border-hair bg-surface px-3 text-xs text-ink outline-none focus:border-accent"
            >
              <option value="all">All outcomes</option>
              <option value="resolved">Resolved</option>
              <option value="pending">Pending</option>
            </select>
          </label>
        </div>
      </div>

      {pageRows.length ? (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[860px] text-sm tabular-nums">
            <thead>
              <tr className="border-b border-hair text-left font-mono text-[11px] uppercase text-ink-mute">
                <th className="px-4 py-2.5 font-normal">Date</th>
                <th className="py-2.5 pr-4 font-normal">Ticker</th>
                <th className="py-2.5 pr-4 font-normal">Stance</th>
                <th className="py-2.5 pr-4 text-right font-normal">Conviction</th>
                <th className="py-2.5 pr-4 text-right font-normal">Return</th>
                <th className="py-2.5 pr-4 text-right font-normal">Raw alpha</th>
                <th className="py-2.5 pr-4 text-right font-normal">Decision edge</th>
                <th className="py-2.5 pr-4 font-normal">Reasoning</th>
              </tr>
            </thead>
            <tbody>
              {pageRows.map((decision) => {
                const edge = decision.alpha == null
                  ? null
                  : directionAdjustedAlpha(decision.alpha, decision.stance);
                return (
                  <tr key={decision.id} className="border-b border-hair/50 align-top" data-audit-row="true">
                    <td className="px-4 py-3 font-mono text-[11px] text-ink-mute">{decision.run_date ?? '—'}</td>
                    <td className="py-3 pr-4 font-medium text-ink">{decision.ticker}</td>
                    <td className="py-3 pr-4 capitalize text-ink-soft">{decision.stance ?? '—'}</td>
                    <td className="py-3 pr-4 text-right text-ink-soft">{decision.conviction ?? '—'}</td>
                    <td className={`py-3 pr-4 text-right ${signColorClass(decision.actual_return)}`}>
                      {fmtPct(decision.actual_return == null ? null : decision.actual_return * 100)}
                    </td>
                    <td className={`py-3 pr-4 text-right ${signColorClass(decision.alpha)}`}>
                      {fmtPct(decision.alpha == null ? null : decision.alpha * 100)}
                    </td>
                    <td className={`py-3 pr-4 text-right ${signColorClass(edge)}`}>
                      {fmtPct(edge == null ? null : edge * 100)}
                    </td>
                    <td className="py-3 pr-4">
                      {decision.thesis || decision.reflection ? (
                        <details className="max-w-md text-xs text-ink-soft">
                          <summary className="cursor-pointer text-ink-soft hover:text-ink">Review</summary>
                          <div className="mt-2 space-y-2 border-l border-hair pl-3 leading-relaxed">
                            {decision.thesis ? <p><strong className="text-ink">Thesis:</strong> {decision.thesis}</p> : null}
                            {decision.reflection ? <p><strong className="text-ink">Reflection:</strong> {decision.reflection}</p> : null}
                          </div>
                        </details>
                      ) : (
                        <span className="text-ink-mute">—</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="px-4 py-10 text-center text-sm text-ink-mute">No decisions match these filters.</p>
      )}

      <footer className="flex items-center justify-between gap-4 px-4 py-3">
        <span className="font-mono text-[11px] text-ink-mute">{first}–{last} of {filtered.length}</span>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => setPage((value) => Math.max(0, value - 1))}
            disabled={activePage === 0}
            className="p-2 text-ink-soft transition-colors hover:text-ink disabled:cursor-not-allowed disabled:opacity-30"
            aria-label="Previous audit page"
            title="Previous page"
          >
            <ChevronLeft className="size-4" aria-hidden="true" />
          </button>
          <span className="min-w-16 text-center font-mono text-[11px] text-ink-mute">
            {activePage + 1} / {pageCount}
          </span>
          <button
            type="button"
            onClick={() => setPage((value) => Math.min(pageCount - 1, value + 1))}
            disabled={activePage >= pageCount - 1}
            className="p-2 text-ink-soft transition-colors hover:text-ink disabled:cursor-not-allowed disabled:opacity-30"
            aria-label="Next audit page"
            title="Next page"
          >
            <ChevronRight className="size-4" aria-hidden="true" />
          </button>
        </div>
      </footer>
    </section>
  );
}