'use client';

import { useDeferredValue, useMemo, useState } from 'react';
import { ChevronLeft, ChevronRight, Search, X } from 'lucide-react';
import {
  Button,
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
  IconButton,
  Input,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@digithings/ui/ui';
import type { TableRow as DbTableRow } from '@/lib/database.types';
import { directionAdjustedAlpha } from '@/lib/decision-scorecard';
import { fmtPct, signColorClass } from '@/components/observability/shared';

const PAGE_SIZE = 25;

export default function DecisionAudit({
  decisions,
}: {
  decisions: DbTableRow<'decision_log'>[];
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
          <Label className="relative min-w-0">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-ink-mute" aria-hidden="true" />
            <Input
              type="search"
              value={query}
              onChange={(event) => {
                setQuery(event.target.value);
                resetPage();
              }}
              placeholder="Search decisions"
              aria-label="Search decisions"
              className="h-9 border-hair pl-9 pr-8 text-ink focus:border-accent"
            />
            {query ? (
              <Button
                type="button"
                variant="ghost"
                size="icon-xs"
                onClick={() => {
                  setQuery('');
                  resetPage();
                }}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-ink-mute hover:text-ink"
                aria-label="Clear decision search"
                title="Clear search"
              >
                <X className="size-3.5" aria-hidden="true" />
              </Button>
            ) : null}
          </Label>

          <Select
            value={stance}
            onValueChange={(next) => {
              if (typeof next === 'string') setStance(next);
              resetPage();
            }}
          >
            <SelectTrigger
              aria-label="Filter by stance"
              className="h-9 border-hair bg-surface px-3 text-xs capitalize text-ink"
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All stances</SelectItem>
              {stances.map((item) => <SelectItem key={item} value={item}>{item}</SelectItem>)}
            </SelectContent>
          </Select>

          <Select
            value={status}
            onValueChange={(next) => {
              if (typeof next === 'string') setStatus(next);
              resetPage();
            }}
          >
            <SelectTrigger
              aria-label="Filter by status"
              className="h-9 border-hair bg-surface px-3 text-xs text-ink"
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All outcomes</SelectItem>
              <SelectItem value="resolved">Resolved</SelectItem>
              <SelectItem value="pending">Pending</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {pageRows.length ? (
        <Table className="min-w-[860px] text-sm tabular-nums">
          <TableHeader>
            <TableRow className="text-left font-mono text-[11px] uppercase text-ink-mute hover:bg-transparent">
              <TableHead className="h-auto px-4 py-2.5 font-normal">Date</TableHead>
              <TableHead className="h-auto py-2.5 pr-4 font-normal">Ticker</TableHead>
              <TableHead className="h-auto py-2.5 pr-4 font-normal">Stance</TableHead>
              <TableHead numeric className="h-auto py-2.5 pr-4 font-normal">Conviction</TableHead>
              <TableHead numeric className="h-auto py-2.5 pr-4 font-normal">Return</TableHead>
              <TableHead numeric className="h-auto py-2.5 pr-4 font-normal">Raw alpha</TableHead>
              <TableHead numeric className="h-auto py-2.5 pr-4 font-normal">Decision edge</TableHead>
              <TableHead className="h-auto py-2.5 pr-4 font-normal">Reasoning</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {pageRows.map((decision) => {
              const edge = decision.alpha == null
                ? null
                : directionAdjustedAlpha(decision.alpha, decision.stance);
              return (
                <TableRow key={decision.id} className="border-hair/50 align-top" data-audit-row="true">
                  <TableCell className="px-4 py-3 font-mono text-[11px] text-ink-mute">{decision.run_date ?? '—'}</TableCell>
                  <TableCell className="py-3 pr-4 font-medium text-ink">{decision.ticker}</TableCell>
                  <TableCell className="py-3 pr-4 capitalize text-ink-soft">{decision.stance ?? '—'}</TableCell>
                  <TableCell numeric className="py-3 pr-4 text-ink-soft">{decision.conviction ?? '—'}</TableCell>
                  <TableCell numeric className={`py-3 pr-4 ${signColorClass(decision.actual_return)}`}>
                    {fmtPct(decision.actual_return == null ? null : decision.actual_return * 100)}
                  </TableCell>
                  <TableCell numeric className={`py-3 pr-4 ${signColorClass(decision.alpha)}`}>
                    {fmtPct(decision.alpha == null ? null : decision.alpha * 100)}
                  </TableCell>
                  <TableCell numeric className={`py-3 pr-4 ${signColorClass(edge)}`}>
                    {fmtPct(edge == null ? null : edge * 100)}
                  </TableCell>
                  <TableCell className="py-3 pr-4 whitespace-normal">
                    {decision.thesis || decision.reflection ? (
                      <Collapsible className="max-w-md text-xs text-ink-soft">
                        <CollapsibleTrigger className="text-ink-soft hover:text-ink">Review</CollapsibleTrigger>
                        <CollapsibleContent keepMounted>
                          <div className="mt-2 space-y-2 border-l border-hair pl-3 leading-relaxed">
                            {decision.thesis ? <p><strong className="text-ink">Thesis:</strong> {decision.thesis}</p> : null}
                            {decision.reflection ? <p><strong className="text-ink">Reflection:</strong> {decision.reflection}</p> : null}
                          </div>
                        </CollapsibleContent>
                      </Collapsible>
                    ) : (
                      <span className="text-ink-mute">—</span>
                    )}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      ) : (
        <p className="px-4 py-10 text-center text-sm text-ink-mute">No decisions match these filters.</p>
      )}

      <footer className="flex items-center justify-between gap-4 px-4 py-3">
        <span className="font-mono text-[11px] text-ink-mute">{first}–{last} of {filtered.length}</span>
        <div className="flex items-center gap-1">
          <IconButton
            onClick={() => setPage((value) => Math.max(0, value - 1))}
            disabled={activePage === 0}
            className="disabled:opacity-30"
            aria-label="Previous audit page"
            title="Previous page"
          >
            <ChevronLeft className="size-4" aria-hidden="true" />
          </IconButton>
          <span className="min-w-16 text-center font-mono text-[11px] text-ink-mute">
            {activePage + 1} / {pageCount}
          </span>
          <IconButton
            onClick={() => setPage((value) => Math.min(pageCount - 1, value + 1))}
            disabled={activePage >= pageCount - 1}
            className="disabled:opacity-30"
            aria-label="Next audit page"
            title="Next page"
          >
            <ChevronRight className="size-4" aria-hidden="true" />
          </IconButton>
        </div>
      </footer>
    </section>
  );
}