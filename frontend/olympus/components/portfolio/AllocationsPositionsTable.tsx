'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { ArrowUpRight } from 'lucide-react';
import { pnlColor } from '@/components/ui';
import type { BookReconciliation } from '@/lib/book-reconciliation';
import { formatQuoteAge, valuePosition, type Valuation } from '@/lib/live-valuation';
import { useLivePrices } from '@/lib/hooks/use-live-prices';
import RiskEnvelopeCell from '@/components/portfolio/RiskEnvelopeCell';
import { formatAllocationCategory } from '@/components/portfolio/tabs/palette-and-format';

/*
 * Ruling (#1450 F4 batch D): stays a local table. Sector group rows, ReactNode
 * cells (conviction meter, risk envelope, signed decision badge) and responsive
 * column hiding are outside the promoted <SortableTable/> leaderboard grammar —
 * see lib/TABLES.md. (The click-to-expand PositionDrilldown this ruling also
 * cited went away with the orphaned Performance tab in #1747; this table has
 * had no row expansion since.)
 *
 * #1833 — the live valuation overlay. Each row's since-entry return is derived IN THE BROWSER
 * from public.prices_live and persisted NOWHERE: this file reads, and never writes, and the
 * close-keyed record (`positions.current_price` / `metrics_as_of`, written nightly by
 * refresh_performance_metrics.py) stays the sole input to NAV history, returns and attribution.
 * See lib/live-valuation.ts for the invariant and why breaking it is invisible.
 *
 * The figure rides in the risk column rather than a restored "Unrealized" column: #1664
 * (8e345b83) narrowed this table to five columns — inventory, allocation, risk envelope,
 * dossier — and its test pins that shape. Co-locating the number with #1834's marker on the
 * stop↔target track keeps the change additive, and the marker is that number drawn.
 */
export default function AllocationsPositionsTable(props: {
  reconciliation: BookReconciliation;
  /**
   * Reference instant for the freshness gate. Omit it in the app — the ticking clock below
   * supplies it. Tests pass a fixed value so a label assertion is not a clock assertion.
   */
  nowMs?: number;
}) {
  const { reconciliation } = props;
  const searchParams = useSearchParams();
  const selectedTicker = searchParams?.get('ticker')?.toUpperCase() ?? null;
  const rowRefs = useRef<Map<string, HTMLTableRowElement>>(new Map());

  useEffect(() => {
    if (!selectedTicker) return;
    rowRefs.current.get(selectedTicker)?.scrollIntoView({ block: 'center' });
  }, [selectedTicker]);

  const sorted = useMemo(
    () => [...reconciliation.rows].sort((a, b) => b.normalizedWeight - a.normalizedWeight),
    [reconciliation.rows]
  );

  // ONE subscription for the whole table — never per row. Coverage is not guaranteed per
  // ticker (the publisher caps at 25 symbols), so a missing key is normal and every row falls
  // back through valuePosition rather than being blanked.
  const tickers = useMemo(() => sorted.map((p) => p.ticker.toUpperCase()), [sorted]);
  const quotes = useLivePrices(tickers);

  // THE ONLY CLOCK IN THIS FEATURE. lib/live-valuation.ts stays pure and takes the instant as
  // an argument; the default is read here, at the boundary, and once per render so every row is
  // judged against the same instant.
  const ticking = useNowMs();
  const nowMs = props.nowMs ?? ticking;

  return (
    <div
      data-region="positions-table"
      className="flex h-full min-h-0 flex-col border border-hair bg-surface"
    >
      <div className="flex items-center justify-between gap-3 border-b border-hair bg-term-bg px-4 py-3 md:px-6">
        <h3 className="font-display text-xl font-normal tracking-tight text-ink">Positions</h3>
        <span className="font-mono text-[0.62rem] uppercase tracking-wider text-ink-mute">
          allocation · risk
        </span>
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        <table className="w-full table-fixed border-collapse font-mono text-[0.78rem] [font-variant-numeric:tabular-nums]">
          <colgroup>
            <col className="w-[34%] sm:w-[28%]" />
            <col className="hidden w-[18%] sm:table-column" />
            <col className="w-[22%] sm:w-[18%]" />
            <col className="w-[34%] sm:w-[28%]" />
            <col className="w-[10%] sm:w-[8%]" />
          </colgroup>
          <thead className="sticky top-0 z-10 bg-surface">
            <tr className="border-b border-hair text-[0.58rem] font-normal uppercase tracking-[0.1em] text-ink-mute">
              <th className="py-[0.7rem] pl-2 pr-2 text-left font-normal md:pl-4">Holding</th>
              <th className="hidden px-3 py-[0.7rem] text-left font-normal sm:table-cell">Category</th>
              <th className="px-2 py-[0.7rem] text-right font-normal md:px-3">Weight / target</th>
              <th className="px-2 py-[0.7rem] text-right font-normal md:px-3">Stop ↔ target</th>
              <th className="px-2 py-[0.7rem] text-right font-normal md:px-3">
                <span className="sr-only">Dossier</span>
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-hair">
            {sorted.map((p) => {
                  const tickerKey = p.ticker.toUpperCase();
                  const isSelected = selectedTicker === tickerKey;
                  // live quote → close → nothing. Never a 0, never a midpoint. `nowMs` decides
                  // only the LABEL (`isFresh`), never which mark is used or what it computes to.
                  const valuation = valuePosition(p, quotes[tickerKey], nowMs);
                  return (
                      <tr key={p.ticker}
                        ref={(el) => {
                          if (el) rowRefs.current.set(tickerKey, el);
                          else rowRefs.current.delete(tickerKey);
                        }}
                        data-selected={isSelected || undefined}
                        className={`transition-colors hover:bg-ink/[0.03] ${
                          isSelected ? 'bg-accent/[0.06] shadow-[inset_2px_0_0_var(--accent)]' : ''
                        }`}
                      >
                        <td className="max-w-[13rem] py-3 pl-2 pr-2 md:pl-4">
                          <span className="block font-mono font-semibold text-ink">
                            {p.ticker}
                          </span>
                          {p.name.trim().toUpperCase() !== p.ticker.trim().toUpperCase() ? (
                            <span
                              className="mt-0.5 block truncate text-[0.68rem] text-ink-mute"
                              title={p.name}
                            >
                              {p.name}
                            </span>
                          ) : null}
                          <span className="mt-0.5 block truncate text-[0.64rem] text-ink-mute sm:hidden">
                            {formatAllocationCategory(p.category)}
                          </span>
                        </td>
                        <td className="hidden px-3 py-3 text-left text-xs text-ink-soft sm:table-cell">
                          {formatAllocationCategory(p.category)}
                        </td>
                        <td className="px-2 py-3 text-right md:px-3">
                          <span className="block font-medium">{p.normalizedWeight.toFixed(1)}%</span>
                          <WeightChangeBadge deltaPp={p.weight_delta ?? null} />
                          <span className="mt-0.5 block text-[0.64rem] text-ink-mute">
                            {p.weight_target != null ? `${p.weight_target.toFixed(1)}% target` : 'no target'}
                          </span>
                        </td>
                        <td className="px-2 py-3 md:px-3">
                          <div className="flex flex-col items-end gap-1">
                            <MarkFigure ticker={p.ticker} valuation={valuation} />
                            <RiskEnvelopeCell
                              stopLossPct={p.stop_loss_pct}
                              targetPctGain={p.target_pct_gain}
                              horizonDays={null}
                              valuation={valuation}
                            />
                          </div>
                        </td>
                        <td className="px-2 py-3 text-right md:px-3">
                          <Link
                            href={`/portfolio/tickers?ticker=${encodeURIComponent(p.ticker.toUpperCase())}`}
                            className="inline-flex h-8 w-8 items-center justify-center text-ink-mute hover:text-accent"
                            title={`Open ${p.ticker} dossier`}
                            aria-label={`Open ${p.ticker} dossier`}
                          >
                            <ArrowUpRight size={15} aria-hidden />
                          </Link>
                        </td>
                      </tr>
                  );
                })}
            {reconciliation.rows.length === 0 && (
              <tr>
                <td colSpan={5} className="text-center py-10 text-ink-mute">
                  No active positions
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/** How often the freshness clock advances. See {@link useNowMs}. */
const CLOCK_TICK_MS = 30_000;

/**
 * A wall clock that advances on its own, for the freshness labels to age against.
 *
 * WHY IT HAS TO TICK, rather than being sampled once. A label derived from a clock read at
 * mount would never go stale: a ticker that freezes AFTER mount keeps a `quoted_at` newer than
 * the sampled instant, so its age stays 0 and it reads "live" for as long as the tab is open —
 * which is exactly the per-ticker mid-session freeze this gate exists for. Realtime re-renders
 * do not cover it either: when the whole feed goes quiet (at the close, or when it breaks) no
 * quote arrives, so nothing would re-render and the last labels would sit there overnight.
 *
 * WHY NOT `Date.now()` IN THE RENDER BODY: `react-hooks/purity` is an error in this config, and
 * rightly — an impure render read is unstable across re-renders. The clock is read in a
 * `useState` LAZY INITIALIZER for the first sample and in the interval's effect callback for every
 * one after; both are legal places for it, and the value enters render only as state. (An earlier
 * revision of this comment said "inside an effect callback" alone, which understated the
 * initializer — mentioning it matters, because moving that read into the render body to "simplify"
 * is exactly what the lint rule forbids.)
 *
 * `CLOCK_TICK_MS` is 30s against a five-minute threshold, so a label is at most 30s late, and
 * the cost is one state update per 30s for the whole table. The lazy initial value differs
 * between the static prerender and hydration, which is safe here and not by luck: the first
 * render on both sides has an EMPTY quote map, so no row takes the live branch and no
 * clock-derived text is in either output (the close branch is dated by day, never by age).
 */
function useNowMs(intervalMs = CLOCK_TICK_MS): number {
  const [nowMs, setNowMs] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNowMs(Date.now()), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);
  return nowMs;
}

/**
 * The since-entry return at the current moment, with the provenance that makes it readable.
 *
 * ATTRIBUTION IS PART OF THE FEATURE, not decoration: a live figure and a close figure that
 * render identically leave the reader unable to tell current from stale (the ambiguity #1750
 * flags for frozen documents). So the source rides beside the number as a word — `live` or
 * `close`, which is legible without colour and survives a monochrome print — the exact
 * timestamp sits in the tooltip for mouse users, and the whole sentence is in an sr-only span
 * for assistive tech. Colour (via `pnlColor`) only ever repeats the sign, which the leading
 * `+`/`−` already carries.
 *
 * THREE LABELS, NOT TWO, because "a `prices_live` row exists" and "this number is current" are
 * different facts and the word "live" is a claim about the second. A quote past
 * `LIVE_QUOTE_FRESH_MS` still supplies the figure — it is the best mark available and dropping
 * it would show LESS — but it loses the word and gets its age and instant instead. Whichever of
 * the three it is, the value is identical; only the label moves. The gate is
 * `source === 'live' && isFresh`: `!isFresh` alone is true of every close as well.
 *
 * `unavailable` renders the table's em-dash convention. NOT 0% — a fabricated zero reads as a
 * real "flat" — and not a blank cell either.
 */
/**
 * Signed change in this holding's size since the previous book date, in percentage points.
 *
 * Renders NOTHING when there is no rate of change to show — a brand-new position, a removed one,
 * or a hold that did not move. That is the owner's rule for #1850: *"if it was completely removed
 * or if it's a brand new position, then there isn't a rate of change to it. It's just a brand new
 * position or it's gone."* `weight_delta` is null in exactly those cases (see
 * `lib/holding-weight-change.ts`), so an absent badge is the honest rendering rather than a `0.0pp`
 * that would read as a measured non-move.
 */
function WeightChangeBadge({ deltaPp }: { deltaPp: number | null }) {
  if (deltaPp === null || Math.abs(deltaPp) < 0.05) return null;
  const up = deltaPp > 0;
  return (
    <span
      // Neutral `text-ink-soft`, matching HoldingsActivityTable's weight-change column, NOT
      // text-up/text-down: tokens.css reserves --up/--down for P&L semantics, and a position
      // getting bigger is not a gain. The sign carries the direction.
      className="mt-0.5 block font-mono text-[0.64rem] text-ink-soft"
      title={`${up ? 'Added' : 'Trimmed'} ${Math.abs(deltaPp).toFixed(1)} percentage points since the previous book`}
    >
      {up ? '+' : '−'}
      {Math.abs(deltaPp).toFixed(1)}pp
    </span>
  );
}

function MarkFigure({ ticker, valuation }: { ticker: string; valuation: Valuation }) {
  const pct = valuation.unrealizedPct;
  if (valuation.source === 'unavailable' || pct == null || !Number.isFinite(pct)) {
    return (
      <span className="font-mono text-[11px] text-ink-mute">
        <span aria-hidden>—</span>
        <span className="sr-only">{`${ticker}: no live quote and no closing mark, so no return is shown.`}</span>
      </span>
    );
  }
  const signed = `${pct >= 0 ? '+' : ''}${pct.toFixed(1)}%`;
  const fromQuote = valuation.source === 'live';
  const isCurrent = fromQuote && valuation.isFresh;
  const age = formatQuoteAge(valuation.ageMs);
  const detail = attributionDetail(valuation);
  // The visible marker is a word (or a word plus an age) in every branch — never a colour, and
  // never the bare "live" on a quote that stopped advancing.
  const badge = isCurrent ? 'live' : fromQuote ? (age ? `stale ${age}` : 'stale') : 'close';
  const lead = isCurrent ? 'Live' : fromQuote ? 'Stale quote' : 'Last close';
  const provenance = isCurrent
    ? 'from a live quote'
    : fromQuote
      ? `from a quote that has not advanced${age ? ` in ${age}` : ''}`
      : 'from the last official close';
  return (
    <span
      className="flex items-baseline gap-1"
      title={`${lead} · ${signed} since entry · ${detail}`}
    >
      <span
        className={`font-mono text-[11px] font-medium tabular-nums ${pnlColor(pct)}`}
        aria-hidden
      >
        {signed}
      </span>
      <span
        className="font-mono text-[0.55rem] uppercase tracking-[0.12em] text-ink-mute"
        aria-hidden
      >
        {badge}
      </span>
      <span className="sr-only">
        {`${ticker}: ${signed} since entry, ${provenance}, ${detail}.`}
      </span>
    </span>
  );
}

/**
 * The as-of phrase for a valuation, formatted from the ISO string ONLY. It is what a stale
 * quote gets INSTEAD of the word "live" — the instant, stated exactly, rather than a claim.
 *
 * Deliberately not `toLocale*`: this table is prerendered by the static export (`output:
 * "export"`) and then hydrated in a browser on some other timezone, so a locale-formatted
 * stamp would differ between the two renders and trip a hydration mismatch. UTC is also the
 * honest unit here — `quoted_at` is the exchange's tick time, not the reader's wall clock.
 */
function attributionDetail(valuation: Valuation): string {
  const asOf = valuation.asOf ?? '';
  const day = asOf.slice(0, 10);
  if (valuation.source !== 'live') {
    return day ? `official close of ${day}` : 'official close, date unknown';
  }
  const parsed = Date.parse(asOf);
  if (!Number.isFinite(parsed)) return asOf ? `quoted at ${asOf}` : 'quote time unknown';
  const iso = new Date(parsed).toISOString();
  return `quoted ${iso.slice(11, 16)} UTC on ${iso.slice(0, 10)}`;
}
