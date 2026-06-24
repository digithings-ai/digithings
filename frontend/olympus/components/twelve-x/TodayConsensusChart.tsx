'use client';

import { useMemo, useState } from 'react';
import { latestConsensusAverages } from '@/lib/twelve-x/consensus-derive';
import { currencyColor, scoreColorClass } from '@/lib/twelve-x/consensus-bar';
import { G10_CURRENCIES } from '@/lib/twelve-x/types';
import type { FxConsensusSnapshotRow } from '@/lib/twelve-x/types';
import { ConsensusScoreBar } from './ConsensusScoreBars';

/**
 * The Today page's "Consensus average" chart (frozen visual-spec redesign #1).
 *
 * For each G10 currency it draws a divergent bar whose fill is the trailing
 * consensus average (last 5 runs), with three legend-coded reference ticks
 * overlaid — today's raw actual, yesterday's average and the ~5-days-ago
 * average — so a reader sees both the smoothed level and the actual-vs-average
 * rate of change at a glance. A momentum arrow (today's actual minus the
 * average) sits at the end of each row.
 *
 * A "Proposed | Current" toggle swaps this view for the prior design (a
 * horizontally-scrollable strip of movers cards: code, latest raw score and a
 * delta triangle vs the immediately prior run). Both views derive entirely from
 * `series`, so the component takes a single prop.
 */

type TodayView = 'proposed' | 'current';

export interface TodayConsensusChartProps {
  /** Per-currency consensus time series (one row per currency per run_date). */
  series: FxConsensusSnapshotRow[];
}

interface CurrencyRow {
  currency: string;
  avgNow: number | null;
  actualNow: number | null;
  avgYesterday: number | null;
  avgAgo: number | null;
  momentum: number | null;
  /** Raw score one run before the latest (for the Current movers card). */
  prevActual: number | null;
}

/** Format a score as a signed 2-dp string, or an em dash for null. */
function fmtSigned(v: number | null): string {
  if (v === null || !Number.isFinite(v)) return '—';
  return `${v >= 0 ? '+' : ''}${v.toFixed(2)}`;
}

/** Score → directional text-color class, neutral (`null`) → muted. */
function valueColor(v: number | null): string {
  if (v === null || !Number.isFinite(v)) return 'text-text-muted';
  return scoreColorClass(v);
}

/** Momentum → arrow glyph + color class (▲ up / ▼ down / · flat). */
function momentumPresentation(m: number | null): { arrow: string; cls: string } {
  if (m === null || !Number.isFinite(m) || m === 0) {
    return { arrow: '·', cls: 'text-text-secondary' };
  }
  return m > 0
    ? { arrow: '▲', cls: 'text-fin-green' }
    : { arrow: '▼', cls: 'text-fin-red' };
}

export function TodayConsensusChart({ series }: TodayConsensusChartProps) {
  const [view, setView] = useState<TodayView>('proposed');

  // Currencies present, in canonical G10 order, with any extras sorted after.
  const currencies = useMemo<string[]>(() => {
    const present = new Set(series.map((r) => r.currency));
    const ordered = G10_CURRENCIES.filter((c) => present.has(c));
    const orderedSet = new Set<string>(ordered);
    const extras = [...present].filter((c) => !orderedSet.has(c)).sort();
    return [...ordered, ...extras];
  }, [series]);

  // Per-currency: ascending-by-run-date score points → latest averages + prior.
  const rows = useMemo<CurrencyRow[]>(() => {
    return currencies.map((currency) => {
      const points = series
        .filter((r) => r.currency === currency)
        .sort((a, b) => a.run_date.localeCompare(b.run_date))
        .map((r) => ({ score: r.score }));
      const { avgNow, actualNow, avgYesterday, avgAgo, momentum } =
        latestConsensusAverages(points);
      const prevActual = points.length >= 2 ? points[points.length - 2].score : null;
      return { currency, avgNow, actualNow, avgYesterday, avgAgo, momentum, prevActual };
    });
  }, [series, currencies]);

  const hasData = rows.length > 0;

  return (
    <section className="glass-card p-4 flex flex-col">
      <div className="flex items-center gap-3 flex-wrap mb-3.5">
        <h2 className="section-eyebrow soft text-text-secondary text-[13px] font-semibold tracking-wide">
          Consensus average
        </h2>
        <div
          className="ml-auto inline-flex rounded-lg border border-border-subtle overflow-hidden"
          role="group"
          aria-label="Design version"
        >
          <button
            type="button"
            data-view="proposed"
            aria-pressed={view === 'proposed'}
            onClick={() => setView('proposed')}
            className={`px-3 py-1.5 text-[11.5px] font-medium transition-colors border-r border-border-subtle ${
              view === 'proposed'
                ? 'bg-fin-blue/15 text-fin-blue'
                : 'text-text-secondary hover:text-text-primary hover:bg-white/[0.03]'
            }`}
          >
            Proposed
          </button>
          <button
            type="button"
            data-view="current"
            aria-pressed={view === 'current'}
            onClick={() => setView('current')}
            className={`px-3 py-1.5 text-[11.5px] font-medium transition-colors ${
              view === 'current'
                ? 'bg-fin-blue/15 text-fin-blue'
                : 'text-text-secondary hover:text-text-primary hover:bg-white/[0.03]'
            }`}
          >
            Current
          </button>
        </div>
      </div>

      {!hasData ? (
        <p className="text-xs text-text-muted py-6 text-center">
          No consensus history yet — bars appear once a run is recorded.
        </p>
      ) : view === 'proposed' ? (
        <>
          <div className="tc-rows grid gap-2.5 mt-1">
            {rows.map((r) => {
              const mom = momentumPresentation(r.momentum);
              return (
                <div key={r.currency} className="tc-row flex items-center gap-2.5">
                  <span
                    className="font-mono font-semibold text-[13px] min-w-[34px]"
                    style={{ color: currencyColor(r.currency) }}
                  >
                    {r.currency}
                  </span>
                  <div className="flex-1 min-w-0">
                    <ConsensusScoreBar
                      value={r.avgNow ?? 0}
                      markers={[
                        { value: r.actualNow, kind: 'actual', label: "Today's actual" },
                        { value: r.avgYesterday, kind: 'prior', label: "Yesterday's avg" },
                        { value: r.avgAgo, kind: 'ago', label: '5 days ago avg' },
                      ]}
                    />
                  </div>
                  <span
                    className={`font-mono tabular-nums text-right text-[12.5px] w-[44px] ${valueColor(
                      r.avgNow
                    )}`}
                  >
                    {fmtSigned(r.avgNow)}
                  </span>
                  <span
                    className={`font-mono tabular-nums text-right text-[11.5px] w-[52px] ${mom.cls}`}
                    title="Today's actual vs consensus average (rate of change)"
                  >
                    {mom.arrow} {fmtSigned(r.momentum)}
                  </span>
                </div>
              );
            })}
          </div>

          <div className="tc-legend flex items-center flex-wrap gap-3.5 mt-3.5 pt-3 border-t border-border-subtle text-[10.5px] text-text-muted">
            <span className="flex items-center gap-1.5">
              <span
                className="inline-block w-4 h-2 rounded-sm bg-fin-green"
                aria-hidden="true"
              />
              Consensus average (bar · green bull / red bear, from zero center)
            </span>
            <span className="flex items-center gap-1.5">
              <span
                className="inline-block w-0.5 h-3 rounded-sm bg-text-primary"
                aria-hidden="true"
              />
              Today&apos;s actual
            </span>
            <span className="flex items-center gap-1.5">
              <span
                className="inline-block w-0.5 h-3 rounded-sm bg-fin-blue"
                aria-hidden="true"
              />
              Yesterday&apos;s avg
            </span>
            <span className="flex items-center gap-1.5">
              <span
                className="inline-block w-0.5 h-3 rounded-sm bg-text-muted"
                aria-hidden="true"
              />
              5 days ago avg
            </span>
            <span className="flex items-center gap-1.5">
              <span className="text-fin-green">▲</span>/<span className="text-fin-red">▼</span> =
              actual vs average (rate of change)
            </span>
          </div>
        </>
      ) : (
        <div className="flex gap-2.5 overflow-x-auto pb-1.5">
          {rows.map((r) => {
            const delta =
              r.actualNow === null || r.prevActual === null ? null : r.actualNow - r.prevActual;
            const tri = momentumPresentation(delta);
            return (
              <div
                key={r.currency}
                className="shrink-0 w-[116px] rounded-lg border border-border-subtle p-3 bg-bg-surface"
              >
                <div
                  className="font-mono font-semibold text-[14px]"
                  style={{ color: currencyColor(r.currency) }}
                >
                  {r.currency}
                </div>
                <div
                  className={`font-mono tabular-nums text-[22px] font-semibold mt-2 mb-1 ${valueColor(
                    r.actualNow
                  )}`}
                >
                  {fmtSigned(r.actualNow)}
                </div>
                <div className={`font-mono text-[12px] flex items-center gap-1 ${tri.cls}`}>
                  {tri.arrow} {fmtSigned(delta)}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}

export default TodayConsensusChart;
