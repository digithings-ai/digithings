'use client';

import { useMemo } from 'react';
import { latestConsensusAverages } from '@/lib/twelve-x/consensus-derive';
import { currencyColor, scoreColorClass } from '@/lib/twelve-x/consensus-bar';
import { G10_CURRENCIES } from '@/lib/twelve-x/types';
import type { FxConsensusSnapshotRow } from '@/lib/twelve-x/types';
import { ConsensusScoreBar } from './ConsensusScoreBars';
import { TwelveXSectionHeading } from './TwelveXSectionHeading';

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
 * The headline value per row is the trailing 5-run average (`avgNow`), shown
 * with a small "avg" unit cue and a subtitle, to make explicit that Today
 * intentionally smooths over 5 runs — the Consensus tab shows the raw latest
 * score, so the two differ by design. Everything derives from `series`, so the
 * component takes a single prop.
 */

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
}

/** Format a score as a signed 2-dp string, or an em dash for null. */
function fmtSigned(v: number | null): string {
  if (v === null || !Number.isFinite(v)) return '—';
  return `${v >= 0 ? '+' : ''}${v.toFixed(2)}`;
}

/** Score → directional text-color class, neutral (`null`) → muted. */
function valueColor(v: number | null): string {
  if (v === null || !Number.isFinite(v)) return 'text-ink-mute';
  return scoreColorClass(v);
}

/** Momentum → arrow glyph + color class (▲ up / ▼ down / · flat). */
function momentumPresentation(m: number | null): { arrow: string; cls: string } {
  if (m === null || !Number.isFinite(m) || m === 0) {
    return { arrow: '·', cls: 'text-ink-soft' };
  }
  return m > 0
    ? { arrow: '▲', cls: 'text-up' }
    : { arrow: '▼', cls: 'text-down' };
}

export function TodayConsensusChart({ series }: TodayConsensusChartProps) {
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
      return { currency, avgNow, actualNow, avgYesterday, avgAgo, momentum };
    });
  }, [series, currencies]);

  const hasData = rows.length > 0;

  return (
    <section className="glass-card p-4 flex flex-col flex-1">
      <div className="mb-3.5">
        <TwelveXSectionHeading>Consensus average</TwelveXSectionHeading>
        <p className="mt-1 text-[11px] text-ink-mute">
          Trailing 5-run average — raw latest scores are on the Consensus tab.
        </p>
      </div>

      {!hasData ? (
        <p className="text-xs text-ink-mute py-6 text-center">
          No consensus history yet — bars appear once a run is recorded.
        </p>
      ) : (
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
                    className={`font-mono tabular-nums text-right text-[12.5px] w-[60px] ${valueColor(
                      r.avgNow
                    )}`}
                  >
                    {fmtSigned(r.avgNow)}
                    <span className="ml-1 text-[9.5px] font-normal text-ink-mute">avg</span>
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

          <div className="tc-legend flex items-center flex-wrap gap-3.5 mt-3.5 pt-3 border-t border-hair text-[10.5px] text-ink-mute">
            <span className="flex items-center gap-1.5">
              <span
                className="inline-block w-4 h-2 rounded-sm bg-up"
                aria-hidden="true"
              />
              Consensus average (bar · green bull / red bear, from zero center)
            </span>
            <span className="flex items-center gap-1.5">
              <span
                className="inline-block w-0.5 h-3 rounded-sm bg-ink"
                aria-hidden="true"
              />
              Today&apos;s actual
            </span>
            <span className="flex items-center gap-1.5">
              <span
                className="inline-block w-0.5 h-3 rounded-sm bg-accent"
                aria-hidden="true"
              />
              Yesterday&apos;s avg
            </span>
            <span className="flex items-center gap-1.5">
              <span
                className="inline-block w-0.5 h-3 rounded-sm bg-ink-mute"
                aria-hidden="true"
              />
              5 days ago avg
            </span>
            <span className="flex items-center gap-1.5">
              <span className="text-up">▲</span>/<span className="text-down">▼</span> =
              actual vs average (rate of change)
            </span>
          </div>
        </>
      )}
    </section>
  );
}

export default TodayConsensusChart;
