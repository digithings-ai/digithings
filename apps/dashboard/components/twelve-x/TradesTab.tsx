'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ClipboardList } from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from '@digithings/ui';
import {
  Button,
  SegmentedControl,
  Slider,
  Table,
  TableBody,
  TableHead,
  TableHeader,
  TableRow,
} from '@digithings/ui/ui';
import type { FxIdeaEvalRow, FxTradeIdeaRow } from '@/lib/twelve-x/types';
import {
  annotateLevelUpdates,
  assembleTradeHistory,
  biasLabel,
  closeCounts,
  closeReason,
  displayableTradeHistory,
  filterTradeHistory,
  finalResult,
  formatHoldPct,
  formatPctRight,
  sortTradeHistory,
  summarizeFilteredTrades,
  tradeResult,
  uniqueBoards,
  uniquePairs,
  type ResultFilter,
  type SortDir,
  type TradeHistoryFilters,
  type TradeHistoryRow,
  type TradeResult,
  type TradeSortKey,
} from '@/lib/twelve-x/trade-history';
import BoardDateRangeFilter from './BoardDateRangeFilter';
import ExcursionRangeCell from './ExcursionRangeCell';

const RESULT_FILTERS: { key: ResultFilter; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'wins', label: 'Wins' },
  { key: 'losses', label: 'Losses' },
  { key: 'live', label: 'Live' },
];

/** Slider span for min |Impact| (percent points). Default 0 = no floor. */
const IMPACT_MIN_PCT = 0;
const IMPACT_MAX_PCT = 2;
const IMPACT_STEP_PCT = 0.05;
const IMPACT_DEFAULT_PCT = 0;

/** Initial rows roughly fill a tall viewport; more load on scroll. */
const PAGE_SIZE = 40;

function formatImpactThresholdLabel(pct: number): string {
  const shown = Number.isInteger(pct) ? pct.toFixed(0) : pct.toFixed(2).replace(/0+$/, '').replace(/\.$/, '');
  return `|Impact| ≥ ${shown}%`;
}

function ResultPill({ result }: { result: TradeResult }) {
  const toneClass =
    result === 'right'
      ? 'border-accent text-accent'
      : result === 'wrong'
        ? 'border-warn text-warn'
        : result === 'closed'
          ? 'border-ink/40 text-ink-mute'
          : 'border-ink text-ink';
  const label =
    result === 'right'
      ? 'RIGHT'
      : result === 'wrong'
        ? 'WRONG'
        : result === 'closed'
          ? 'CLOSED'
          : 'LIVE';
  return (
    <span className={`inline-block border px-1.5 font-mono text-[10px] ${toneClass}`}>
      {label}
    </span>
  );
}

function SortHeader({
  label,
  sortKey,
  activeKey,
  sortDir,
  onSort,
  title,
  align = 'left',
}: {
  label: string;
  sortKey: TradeSortKey;
  activeKey: TradeSortKey | null;
  sortDir: SortDir;
  onSort: (key: TradeSortKey) => void;
  title?: string;
  align?: 'left' | 'right';
}) {
  const active = activeKey === sortKey;
  return (
    <TableHead
      numeric={align === 'right'}
      className="h-auto px-3 py-2 font-medium"
      title={title}
      aria-sort={active ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}
    >
      <Button
        type="button"
        variant="ghost"
        size="xs"
        onClick={() => onSort(sortKey)}
        className="h-auto p-0 text-[10px] font-medium transition-colors hover:bg-transparent hover:text-ink"
      >
        {label}
        {active ? (sortDir === 'asc' ? ' ↑' : ' ↓') : ''}
      </Button>
    </TableHead>
  );
}

function PairFilterDropdown({
  value,
  pairs,
  onChange,
}: {
  value: string;
  pairs: readonly string[];
  onChange: (pair: string) => void;
}) {
  const label = value === 'all' ? 'All pairs' : value;
  const active = value !== 'all';
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        type="button"
        aria-label="Filter by pair"
        data-testid="pair-filter"
        className={`border px-2.5 py-1 text-[11px] font-medium transition-colors ${
          active
            ? 'border-accent/40 bg-accent/15 text-accent'
            : 'border-hair text-ink-mute hover:text-ink'
        }`}
      >
        {label}
      </DropdownMenuTrigger>
      <DropdownMenuContent skin="reference" align="start" sideOffset={4} className="max-h-64 min-w-[8rem]">
        <DropdownMenuRadioGroup value={value} onValueChange={onChange}>
          <DropdownMenuRadioItem value="all">All pairs</DropdownMenuRadioItem>
          {pairs.map((p) => (
            <DropdownMenuRadioItem key={p} value={p}>
              {p}
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export default function TradesTab({
  ideas,
  ideaEval,
  onOpenIdea,
}: {
  ideas: FxTradeIdeaRow[];
  ideaEval: FxIdeaEvalRow[];
  /** Open the idea lifecycle sidebar for a row (local state in TwelveXClient). */
  onOpenIdea?: (runDate: string, rank: number) => void;
  /** Kept optional for call-site compat; consensus sections were removed. */
  consensusEval?: unknown;
}) {
  const [resultFilter, setResultFilter] = useState<ResultFilter>('all');
  const [pairFilter, setPairFilter] = useState('all');
  const [boardFrom, setBoardFrom] = useState<string | null>(null);
  const [boardTo, setBoardTo] = useState<string | null>(null);
  const [impactMinPct, setImpactMinPct] = useState(IMPACT_DEFAULT_PCT);
  const [sortKey, setSortKey] = useState<TradeSortKey | null>('generated');
  const [sortDir, setSortDir] = useState<SortDir>('desc');
  /** Scroll window keyed by filter/sort so changing filters resets without an effect. */
  const [scroll, setScroll] = useState({ key: '', count: PAGE_SIZE });
  const sentinelRef = useRef<HTMLDivElement | null>(null);

  const history = useMemo(
    () =>
      displayableTradeHistory(annotateLevelUpdates(assembleTradeHistory(ideas, ideaEval))),
    [ideas, ideaEval],
  );

  const pairs = useMemo(() => uniquePairs(history), [history]);
  const boards = useMemo(() => uniqueBoards(history), [history]);

  const filters: TradeHistoryFilters = useMemo(
    () => ({
      result: resultFilter,
      pair: pairFilter,
      boardFrom,
      boardTo,
      minAbsImpact: impactMinPct / 100,
    }),
    [resultFilter, pairFilter, boardFrom, boardTo, impactMinPct],
  );

  const filtered = useMemo(() => filterTradeHistory(history, filters), [history, filters]);
  const sorted = useMemo(
    () => sortTradeHistory(filtered, sortKey, sortDir),
    [filtered, sortKey, sortDir],
  );
  const summary = useMemo(() => summarizeFilteredTrades(filtered), [filtered]);
  const closeTally = useMemo(() => closeCounts(filtered), [filtered]);

  const scrollKey = `${resultFilter}|${pairFilter}|${boardFrom}|${boardTo}|${impactMinPct}|${sortKey}|${sortDir}`;
  const visibleCount = scroll.key === scrollKey ? scroll.count : PAGE_SIZE;
  const visible = sorted.slice(0, visibleCount);
  const hasMore = visibleCount < sorted.length;

  const loadMore = useCallback(() => {
    setScroll((prev) => {
      const base = prev.key === scrollKey ? prev.count : PAGE_SIZE;
      return { key: scrollKey, count: Math.min(base + PAGE_SIZE, sorted.length) };
    });
  }, [scrollKey, sorted.length]);

  useEffect(() => {
    const el = sentinelRef.current;
    if (!el || !hasMore) return;
    if (typeof IntersectionObserver === 'undefined') return;
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) loadMore();
      },
      { rootMargin: '120px' },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [hasMore, loadMore, visible.length]);

  function onSort(key: TradeSortKey) {
    if (key === sortKey) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir(key === 'pair' || key === 'bias' ? 'asc' : 'desc');
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3 px-1">
        <ClipboardList size={18} className="shrink-0 text-accent" aria-hidden />
        <h2 className="font-display text-2xl tracking-tight text-ink">Trades</h2>
      </div>
      <p className="max-w-2xl px-1 text-xs text-ink-mute">
        Every trade recommendation and whether it worked. A trade stays live until its stop
        or target is touched (first touch wins, ordered by 1h/5m candles), the bookkeeper
        drops it, or a newer board replaces it. Result carries the one-word grade: Right or
        Wrong when a direction resolved (measured at the touched level or exit close when
        filled, directional when the entry never filled), Closed for an ended trade with no
        verdict, and Live while it runs. Status names the close reason — Target, Stop, Both,
        Dropped, or Superseded — and reads Live while the trade runs. Impact pairs the
        excursion range with the return at close where one exists, tagged with its grading
        basis on ended trades or open while live.
      </p>

      {history.length === 0 ? (
        <p className="px-1 text-sm text-ink-mute">
          {ideas.length === 0
            ? 'No trade ideas published yet.'
            : 'No scored trade ideas yet (missing rates / unscored rows are hidden).'}
        </p>
      ) : (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2 px-1" role="group" aria-label="Filter trades">
            <SegmentedControl
              dress="accent"
              aria-label="Filter trades by result"
              options={RESULT_FILTERS.map((f) => ({ value: f.key, label: f.label }))}
              value={resultFilter}
              onChange={setResultFilter}
            />
            <PairFilterDropdown
              value={pairFilter}
              pairs={pairs}
              onChange={setPairFilter}
            />
            <BoardDateRangeFilter
              boards={boards}
              boardFrom={boardFrom}
              boardTo={boardTo}
              onChange={(from, to) => {
                setBoardFrom(from);
                setBoardTo(to);
              }}
            />
            <div className="min-w-[11rem] flex-1 sm:max-w-[16rem]">
              <div className="mb-[0.6rem] flex items-baseline justify-between gap-[0.8rem]">
                <span className="font-mono text-[0.6rem] uppercase tracking-[0.1em] text-ink-mute">
                  Minimum |Impact|
                </span>
                <span className="font-mono text-[0.86rem] tabular-nums text-ink">
                  {formatImpactThresholdLabel(impactMinPct)}
                </span>
              </div>
              <Slider
                value={impactMinPct}
                min={IMPACT_MIN_PCT}
                max={IMPACT_MAX_PCT}
                step={IMPACT_STEP_PCT}
                onValueChange={(v) => setImpactMinPct(v as number)}
                aria-label="Minimum |Impact|"
                title="Hide rows whose absolute Impact is below this threshold"
                data-testid="impact-min-slider"
              />
            </div>
          </div>

          <div
            className="flex flex-wrap gap-x-6 gap-y-2 border border-hair bg-surface/40 px-3 py-2.5"
            data-testid="trades-summary"
            aria-label="Filtered trade summary"
          >
            <Metric label="% right" value={formatPctRight(summary.pctRight)} hint={`${summary.rightCount}/${summary.resolvedCount}`} />
            <Metric
              label="Avg return (rights)"
              value={formatHoldPct(summary.avgReturnRights)}
            />
            <Metric
              label="Avg return (wrongs)"
              value={formatHoldPct(summary.avgReturnWrongs)}
            />
            <Metric label="Target hits" value={String(closeTally.targets)} />
            <Metric label="Stops" value={String(closeTally.stops)} />
            <Metric label="Superseded" value={String(closeTally.superseded)} />
            <Metric label="Dropped" value={String(closeTally.dropped)} />
            <Metric label="Both" value={String(closeTally.both)} />
            <Metric label="No data" value={String(closeTally.noData)} />
            <span className="self-end font-mono text-[10px] text-ink-mute">
              {filtered.length} matching
              {visible.length < filtered.length ? ` · showing ${visible.length}` : ''}
              {summary.liveCount > 0 ? ` · ${summary.liveCount} live` : ''}
            </span>
          </div>

          {filtered.length === 0 ? (
            <p className="px-1 text-sm text-ink-mute">No trades match the current filters.</p>
          ) : (
            <div className="overflow-x-auto border border-hair">
              <Table className="w-full text-xs">
                <TableHeader>
                  <TableRow className="border-hair text-[10px] uppercase tracking-wider text-ink-mute hover:bg-transparent">
                    <SortHeader label="Generated" sortKey="generated" activeKey={sortKey} sortDir={sortDir} onSort={onSort} />
                    <SortHeader label="Pair" sortKey="pair" activeKey={sortKey} sortDir={sortDir} onSort={onSort} />
                    <SortHeader label="Bias" sortKey="bias" activeKey={sortKey} sortDir={sortDir} onSort={onSort} />
                    <SortHeader label="Entry" sortKey="entry" activeKey={sortKey} sortDir={sortDir} onSort={onSort} />
                    <SortHeader label="Stop" sortKey="stop" activeKey={sortKey} sortDir={sortDir} onSort={onSort} />
                    <SortHeader label="Target" sortKey="target" activeKey={sortKey} sortDir={sortDir} onSort={onSort} />
                    <SortHeader
                      label="Active"
                      sortKey="active"
                      activeKey={sortKey}
                      sortDir={sortDir}
                      onSort={onSort}
                      title="Sessions held (days)"
                      align="right"
                    />
                    <SortHeader
                      label="Impact"
                      sortKey="impact"
                      activeKey={sortKey}
                      sortDir={sortDir}
                      onSort={onSort}
                      title="Observed excursion extremes with close mark (P&L %)"
                      align="right"
                    />
                    <SortHeader label="Result" sortKey="result" activeKey={sortKey} sortDir={sortDir} onSort={onSort} />
                    <TableHead className="h-auto px-3 py-2 text-left font-medium">Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody className="divide-y divide-hair">
                  {visible.map((row) => (
                    <TradeRow
                      key={`${row.runDate}-${row.rank}`}
                      row={row}
                      onOpenIdea={onOpenIdea}
                    />
                  ))}
                </TableBody>
              </Table>
              {hasMore ? (
                <div
                  ref={sentinelRef}
                  className="border-t border-hair px-3 py-2 text-center font-mono text-[10px] text-ink-mute"
                  data-testid="trades-scroll-sentinel"
                >
                  Loading more…
                </div>
              ) : null}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Metric({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <div className="min-w-[7rem]">
      <p className="text-[10px] font-medium uppercase tracking-wider text-ink-mute">{label}</p>
      <p className="font-mono text-sm tabular-nums text-ink">
        {value}
        {hint ? <span className="ml-1.5 text-[10px] text-ink-mute">{hint}</span> : null}
      </p>
    </div>
  );
}

function TradeRow({
  row,
  onOpenIdea,
}: {
  row: TradeHistoryRow;
  onOpenIdea?: (runDate: string, rank: number) => void;
}) {
  const result = tradeResult(row);
  const close = closeReason(row);
  const final = finalResult(row);
  if (result === null) return null;
  const openIdea = () => onOpenIdea?.(row.runDate, row.rank);
  // Row-level interactivity (click / Enter / Space) with no role override:
  // `tr` only permits `role="row"`, and overriding it pruned the table
  // semantics (cells lost their column-header association). The row is a
  // focusable, clickable row — not a button — so screen readers keep reading
  // it as a row. #4210.
  return (
    <tr
      tabIndex={0}
      onClick={openIdea}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          openIdea();
        }
      }}
      className="cursor-pointer transition-colors hover:bg-ink/[0.03] focus:outline-none focus-visible:bg-ink/[0.05]" // canon-allow: focusable table row with role="row" (no button role); kit TableRow is not this shell
    >
      <td className="whitespace-nowrap px-3 py-2 font-mono text-ink-mute">
        {row.runDate}
        {row.continuedFrom ? <span className="ml-1">· cont. since {row.continuedFrom}</span> : null}
        {row.levelsUpdated ? (
          <span className="ml-1 text-accent" title={`levels updated vs ${row.levelsUpdatedFrom}`}>
            · updated
          </span>
        ) : null}
      </td>
      <td className="whitespace-nowrap px-3 py-2 text-ink">{row.pair}</td>
      <td className="whitespace-nowrap px-3 py-2 text-ink">{biasLabel(row.direction)}</td>
      <td className="whitespace-nowrap px-3 py-2 font-mono tabular-nums text-ink">
        {row.entryBand ?? '—'}
      </td>
      <td className="whitespace-nowrap px-3 py-2 font-mono tabular-nums text-ink">
        {row.stop ?? '—'}
      </td>
      <td className="whitespace-nowrap px-3 py-2 font-mono tabular-nums text-ink">
        {row.target ?? '—'}
      </td>
      <td className="whitespace-nowrap px-3 py-2 text-right font-mono tabular-nums text-ink">
        {row.sessions ?? '—'}
      </td>
      <td className="whitespace-nowrap px-3 py-2 text-right text-ink">
        <ExcursionRangeCell
          maxAdverse={row.maxAdverse}
          maxFavorable={row.maxFavorable}
          holdReturn={row.holdReturn}
        />
        {final ? (
          <span
            className={`mt-0.5 block font-mono text-[10px] tabular-nums ${
              final.pct > 0 ? 'text-up' : final.pct < 0 ? 'text-down' : 'text-ink-mute'
            }`}
            title={
              final.basis === 'directional'
                ? 'Directional grade — entry never filled'
                : 'Measured at the filled bracket / exit close'
            }
          >
            {formatHoldPct(final.pct)}
            <span className="ml-1 text-ink-mute">· {final.live ? 'open' : (final.basis ?? 'result')}</span>
          </span>
        ) : null}
      </td>
      <td className="whitespace-nowrap px-3 py-2">
        <ResultPill result={result} />
      </td>
      <td className="whitespace-nowrap px-3 py-2 text-ink-mute">
        <span title={close.detail}>{close.label}</span>
      </td>
    </tr>
  );
}
