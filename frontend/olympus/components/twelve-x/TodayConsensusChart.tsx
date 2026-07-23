'use client';

import { useMemo } from 'react';
import { deriveConsensusRows } from '@/lib/twelve-x/consensus-view';
import { currencyColor, scoreColorClass } from '@/lib/twelve-x/consensus-bar';
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
function rateChangePresentation(m: number | null): { arrow: string; label: string } {
  if (m === null || !Number.isFinite(m) || m === 0) {
    return { arrow: '—', label: 'No change from prior run' };
  }
  return m > 0
    ? { arrow: '↑', label: 'Up from prior run' }
    : { arrow: '↓', label: 'Down from prior run' };
}

export function TodayConsensusChart({ series }: TodayConsensusChartProps) {
  // One row per currency, canonical G10 order — from the shared derivation the
  // Consensus tab reads too, so the two surfaces can never disagree.
  const rows = useMemo(() => deriveConsensusRows(series), [series]);

  const hasData = rows.length > 0;

  return (
    <section className="glass-card p-4 flex flex-col flex-1">
      <div className="mb-3.5">
        <TwelveXSectionHeading>Consensus</TwelveXSectionHeading>
      </div>

      {!hasData ? (
        <p className="text-xs text-ink-mute py-6 text-center">
          No consensus history yet — bars appear once a run is recorded.
        </p>
      ) : (
        <>
          <div className="tc-rows grid gap-2.5 mt-1">
            {rows.map((r) => {
              const rateChange = rateChangePresentation(r.priorChange);
              return (
                <div key={r.currency} className="tc-row flex items-center gap-2.5">
                  <span
                    className="font-mono font-semibold text-[13px] min-w-[34px]"
                    style={{ color: currencyColor(r.currency) }}
                  >
                    {r.currency}
                  </span>
                  <div className="flex-1 min-w-0">
                    {/* One tick only: today's actual vs the smoothed fill. The
                        prior-run level is already carried by the momentum arrow
                        + signed delta beside the bar — a second tick read as an
                        unexplained stray line (#1664 follow-up). */}
                    <ConsensusScoreBar
                      value={r.avgNow ?? 0}
                      markers={[{ value: r.actualNow, kind: 'actual', label: "Today's actual" }]}
                    />
                  </div>
                  <span
                    className={`font-mono tabular-nums text-right text-[12.5px] w-[60px] ${valueColor(
                      r.avgNow
                    )}`}
                  >
                    {fmtSigned(r.avgNow)}
                  </span>
                  <span
                    className={`inline-flex w-[72px] items-center justify-end gap-1 font-mono tabular-nums text-right text-[11.5px] ${valueColor(
                      r.priorChange
                    )}`}
                    title={rateChange.label}
                  >
                    <span aria-hidden="true">{rateChange.arrow}</span>
                    <span>{fmtSigned(r.priorChange)}</span>
                  </span>
                </div>
              );
            })}
          </div>

          <div className="tc-legend flex items-center flex-wrap gap-3.5 mt-3.5 pt-3 border-t border-hair text-[10.5px] text-ink-mute">
            <span className="flex items-center gap-1.5">
              <span
                className="inline-block w-4 h-2 rounded-sm bg-accent"
                aria-hidden="true"
              />
              Trailing 5-run average (bar)
            </span>
            <span className="flex items-center gap-1.5">
              <span
                className="inline-block w-0.5 h-3 rounded-sm bg-ink"
                aria-hidden="true"
              />
              Today&apos;s actual
            </span>
          </div>
        </>
      )}
    </section>
  );
}

export default TodayConsensusChart;
