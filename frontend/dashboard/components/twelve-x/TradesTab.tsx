'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ClipboardList } from 'lucide-react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from '@digithings/web';
import type { FxIdeaEvalRow, FxTradeIdeaRow } from '@/lib/twelve-x/types';
import {
  assembleTradeHistory,
  biasLabel,
  displayableTradeHistory,
  filterTradeHistory,
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
        : 'border-ink text-ink';
  const label = result === 'right' ? 'RIGHT' : result === 'wrong' ? 'WRONG' : 'LIVE';
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
    <th
      className={`px-3 py-2 font-medium ${align === 'right' ? 'text-right' : 'text-left'}`}
      title={title}
      aria-sort={active ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}
    >
      <button
        type="button"
        onClick={() => onSort(sortKey)}
        className="hover:text-ink transition-colors"
      >
        {label}
        {active ? (sortDir === 'asc' ? ' ↑' : ' ↓') : ''}
      </button>
    </th>
  );
}

/** DigiWeb-aligned track fill (same recipe as digiweb Slider). */
function impactSliderFill(pct: number): string {
  const span = IMPACT_MAX_PCT - IMPACT_MIN_PCT;
  const filled = span <= 0 ? 0 : ((pct - IMPACT_MIN_PCT) / span) * 100;
  return `linear-gradient(to right, var(--accent) 0 ${filled}%, color-mix(in srgb, var(--ink) 14%, transparent) ${filled}% 100%)`;
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
}: {
  ideas: FxTradeIdeaRow[];
  ideaEval: FxIdeaEvalRow[];
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
    () => displayableTradeHistory(assembleTradeHistory(ideas, ideaEval)),
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
        Every trade recommendation and whether it worked. Each idea stays live until the
        next board that posts the same pair (successor clock). Directional outcomes use
        daily closes only for now — excursion (spike-capture) and level-touch scoring
        follow once the high/low feed lands. Stop / target levels are quoted as published.
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
            {RESULT_FILTERS.map((f) => {
              const on = resultFilter === f.key;
              return (
                <button
                  key={f.key}
                  type="button"
                  data-filter={f.key}
                  aria-pressed={on}
                  onClick={() => setResultFilter(f.key)}
                  className={`border px-2.5 py-1 text-[11px] font-medium transition-colors ${
                    on
                      ? 'border-accent/40 bg-accent/15 text-accent'
                      : 'border-hair text-ink-mute hover:text-ink'
                  }`}
                >
                  {f.label}
                </button>
              );
            })}
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
            <label
              className="flex min-w-[11rem] flex-1 items-center gap-2 text-[11px] text-ink-mute sm:max-w-[16rem]"
              title="Hide rows whose absolute Impact is below this threshold"
            >
              <span className="shrink-0 font-mono tabular-nums text-ink">
                {formatImpactThresholdLabel(impactMinPct)}
              </span>
              <input
                type="range"
                min={IMPACT_MIN_PCT}
                max={IMPACT_MAX_PCT}
                step={IMPACT_STEP_PCT}
                value={impactMinPct}
                onChange={(e) => setImpactMinPct(Number(e.target.value))}
                aria-label="Minimum absolute Impact percent"
                data-testid="impact-min-slider"
                className="fx-impact-slider flex-1"
                style={{ background: impactSliderFill(impactMinPct) }}
              />
            </label>
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
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-hair text-[10px] uppercase tracking-wider text-ink-mute">
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
                      title="Signed hold return if executed (P&L %)"
                      align="right"
                    />
                    <SortHeader label="Result" sortKey="result" activeKey={sortKey} sortDir={sortDir} onSort={onSort} />
                  </tr>
                </thead>
                <tbody className="divide-y divide-hair">
                  {visible.map((row) => (
                    <TradeRow key={`${row.runDate}-${row.rank}`} row={row} />
                  ))}
                </tbody>
              </table>
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

function TradeRow({ row }: { row: TradeHistoryRow }) {
  const result = tradeResult(row);
  if (result === null) return null;
  return (
    <tr>
      <td className="whitespace-nowrap px-3 py-2 font-mono text-ink-mute">{row.runDate}</td>
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
      <td className="whitespace-nowrap px-3 py-2 text-right font-mono tabular-nums text-ink">
        {formatHoldPct(row.holdReturn)}
      </td>
      <td className="whitespace-nowrap px-3 py-2">
        <ResultPill result={result} />
      </td>
    </tr>
  );
}
