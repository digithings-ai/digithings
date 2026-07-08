'use client';

import { useEffect, useMemo, useState, useRef } from 'react';
import { ChevronDown } from 'lucide-react';
import {
  AreaSeries,
  HistogramSeries,
  LineSeries,
  LineStyle,
  createSeriesMarkers,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type SeriesMarker,
  type Time,
} from 'lightweight-charts';
import type { NavChartPoint, PerfChartPoint } from '@/lib/types';
import { PerformanceDrawdownChart } from '@/components/portfolio/performance-drawdown-chart';
import { PerformanceRollingChart } from '@/components/portfolio/performance-rolling-chart';
import type { PerformanceChartView } from '@/lib/performance-series';
import { buildDailyReturnsWithNavIndex } from '@/lib/performance-series';
import {
  EVENT_COLORS,
  comparableLineColor as lineColorForTicker,
  withAlpha,
} from '@/lib/chart-colors';
import { ChartTipShell, toLineData, useChartTip, useLightweightChart } from '@/lib/lw-chart';

const VIEW_OPTIONS: { id: PerformanceChartView; label: string; hint: string }[] = [
  { id: 'nav', label: 'NAV vs comparables', hint: 'Indexed series; legend removes an overlay' },
  { id: 'daily_returns', label: 'Daily returns', hint: 'Day-over-day % with cumulative NAV' },
  { id: 'drawdown', label: 'Drawdown', hint: 'Peak-to-trough underwater %' },
  {
    id: 'rolling',
    label: 'Risk-adjusted',
    hint: 'Period Sharpe & Sortino; optional rolling series when history allows',
  },
];

function eventColorFor(event: string): string {
  if (event === 'OPEN') return EVENT_COLORS.OPEN;
  if (event === 'EXIT') return EVENT_COLORS.EXIT;
  if (event === 'ADD') return EVENT_COLORS.ADD;
  if (event === 'TRIM') return EVENT_COLORS.TRIM;
  return EVENT_COLORS.DEFAULT;
}

function NavComparableChart({
  data,
  comparableKeys,
  onLegendRemoveComparable,
  activityMarkerDates,
  activityEventsByDate,
}: {
  data: PerfChartPoint[];
  comparableKeys: string[];
  onLegendRemoveComparable: (ticker: string) => void;
  /** Dates in range with OPEN/EXIT/TRIM/ADD — muted markers on the NAV series. */
  activityMarkerDates?: string[];
  /** Pre-aggregated events per date for tooltip enrichment. */
  activityEventsByDate?: Record<string, { ticker: string; event: string }[]>;
}) {
  const { containerRef, chart, colors, isAlive } = useLightweightChart();
  const tip = useChartTip(chart, containerRef, isAlive);
  const portfolioRef = useRef<ISeriesApi<'Area'> | null>(null);
  const markersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);

  const byDate = useMemo(() => new Map(data.map((d) => [d.date, d])), [data]);

  /** Activity dates that land on a plotted portfolio point (markers need a value). */
  const markerDates = useMemo(() => {
    if (!activityMarkerDates?.length) return [];
    return activityMarkerDates.filter((d) => typeof byDate.get(d)?.portfolio === 'number').sort();
  }, [activityMarkerDates, byDate]);

  // Series + data — recreated when the range or overlay set changes.
  useEffect(() => {
    if (!chart || data.length < 2) return;
    const portfolio = chart.addSeries(AreaSeries, {
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: false,
      priceFormat: { type: 'custom', formatter: (v: number) => v.toFixed(2), minMove: 0.01 },
    });
    portfolio.setData(toLineData(data, (d) => d.date, (d) => d.portfolio));
    portfolioRef.current = portfolio;
    markersRef.current = createSeriesMarkers(portfolio, []);

    const overlays: ISeriesApi<'Line'>[] = comparableKeys.map((key) => {
      const line = chart.addSeries(LineSeries, {
        color: lineColorForTicker(key),
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        priceLineVisible: false,
        lastValueVisible: false,
      });
      line.setData(
        toLineData(data, (d) => d.date, (d) => {
          const v = d[key];
          return typeof v === 'number' ? v : null;
        })
      );
      return line;
    });

    chart.timeScale().fitContent();
    return () => {
      portfolioRef.current = null;
      markersRef.current = null;
      if (isAlive()) {
        chart.removeSeries(portfolio);
        for (const line of overlays) chart.removeSeries(line);
      }
    };
  }, [chart, data, comparableKeys, isAlive]);

  // Token colors + activity markers — re-applied on theme flips too.
  useEffect(() => {
    portfolioRef.current?.applyOptions({
      lineColor: colors.accent,
      topColor: withAlpha(colors.accent, 0.24),
      bottomColor: withAlpha(colors.accent, 0.02),
    });
    markersRef.current?.setMarkers(
      markerDates.map(
        (d): SeriesMarker<Time> => ({
          time: d as Time,
          position: 'inBar',
          shape: 'circle',
          color: withAlpha(colors.ink, 0.35),
          size: 1,
        })
      )
    );
  }, [colors, data, comparableKeys, markerDates]);

  if (data.length < 2) {
    return (
      <div className="h-full min-h-[280px] flex items-center justify-center text-ink-mute text-sm">
        Need at least two NAV points in this range.
      </div>
    );
  }

  const tipRow = tip ? byDate.get(tip.iso) : undefined;
  const tipEvents = tip ? activityEventsByDate?.[tip.iso] ?? [] : [];

  return (
    <div className="h-full w-full flex flex-col gap-1.5">
      <div className="flex flex-wrap justify-end gap-x-4 gap-y-1 w-full pr-1">
        <span className="inline-flex items-center gap-1.5 text-[11px] text-ink-mute shrink-0">
          <span className="w-2.5 h-2.5 rounded-sm bg-accent/90 shrink-0" />
          Portfolio
        </span>
        {comparableKeys.map((key) => (
          <button
            key={key}
            type="button"
            title="Remove from chart"
            onClick={() => onLegendRemoveComparable(key)}
            className="inline-flex items-center gap-1.5 text-[11px] text-ink-soft hover:text-ink transition-colors shrink-0 cursor-pointer font-mono"
          >
            <svg width={18} height={8} className="shrink-0 overflow-visible" aria-hidden>
              <line
                x1={0}
                y1={4}
                x2={18}
                y2={4}
                stroke={lineColorForTicker(key)}
                strokeWidth={2}
                strokeDasharray="4 3"
              />
            </svg>
            {key}
          </button>
        ))}
      </div>
      <div ref={containerRef} className="relative flex-1 min-h-0">
        {tip && tipRow ? (
          <ChartTipShell tip={tip}>
            <p className="text-ink-soft text-[0.75rem] mb-1">{tip.iso}</p>
            <div className="flex justify-between gap-3">
              <span style={{ color: colors.accent }}>Portfolio NAV</span>
              <span className="font-mono text-ink tabular-nums">
                {typeof tipRow.portfolio === 'number' ? tipRow.portfolio.toFixed(2) : '—'}
              </span>
            </div>
            {comparableKeys.map((key) => {
              const v = tipRow[key];
              return (
                <div key={key} className="flex justify-between gap-3">
                  <span style={{ color: lineColorForTicker(key) }}>{key}</span>
                  <span className="font-mono text-ink tabular-nums">
                    {typeof v === 'number' ? v.toFixed(2) : '—'}
                  </span>
                </div>
              );
            })}
            {tipEvents.length > 0 ? (
              <div className="mt-1.5 pt-1.5 border-t border-hair">
                {tipEvents.map((ev, i) => (
                  <div key={i} className="flex gap-1.5 text-[0.72rem] text-ink-soft">
                    <span style={{ color: eventColorFor(ev.event) }}>{ev.event}</span>
                    <span className="font-mono">{ev.ticker}</span>
                  </div>
                ))}
              </div>
            ) : null}
          </ChartTipShell>
        ) : null}
      </div>
    </div>
  );
}

function ComparableDropdown({
  universe,
  selected,
  maxComparables,
  onAdd,
  onRemove,
  loading,
  error,
}: {
  universe: string[];
  selected: string[];
  maxComparables: number;
  onAdd: (ticker: string) => void;
  onRemove: (ticker: string) => void;
  loading: boolean;
  error: string | null;
}) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState('');
  const rootRef = useRef<HTMLDivElement>(null);

  const filtered = useMemo(() => {
    const qq = q.trim().toUpperCase();
    if (!qq) return universe;
    return universe.filter((t) => t.includes(qq));
  }, [universe, q]);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
        setQ('');
      }
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [open]);

  const atCap = selected.length >= maxComparables;

  const toggleOpen = () => {
    if (open) {
      setOpen(false);
      setQ('');
    } else {
      setQ('');
      setOpen(true);
    }
  };

  return (
    <div ref={rootRef} className="flex flex-wrap items-center gap-2">
      {selected.map((t) => (
        <span
          key={t}
          className="inline-flex items-center gap-0.5 pl-2 pr-1 py-0.5 rounded-md text-[11px] font-mono font-medium border border-accent/35 bg-accent/10 text-accent"
        >
          {t}
          <button
            type="button"
            onClick={() => onRemove(t)}
            className="p-0.5 rounded hover:bg-ink/10 text-ink-soft hover:text-ink leading-none"
            aria-label={`Remove ${t}`}
          >
            ×
          </button>
        </span>
      ))}

      <div className="relative">
        <button
          type="button"
          onClick={toggleOpen}
          className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium border border-hair bg-term-bg text-ink-soft hover:border-accent/40 hover:text-ink transition-colors"
          aria-expanded={open ? 'true' : 'false'}
          aria-haspopup="listbox"
          aria-controls="comparable-ticker-listbox"
        >
          Comparables
          <ChevronDown size={14} className={`opacity-70 transition-transform ${open ? 'rotate-180' : ''}`} />
        </button>

        {open && (
          <div className="absolute left-0 top-full z-[60] mt-1 w-[min(100vw-2rem,18rem)] rounded-lg border border-hair bg-term-bg shadow-xl overflow-hidden">
            <input
              id="comparable-ticker-search"
              type="search"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search all tickers…"
              aria-label="Search tickers in price history"
              className="w-full px-2.5 py-2 text-sm bg-term-bg border-b border-hair text-ink placeholder:text-ink-mute focus:outline-none focus:ring-1 focus:ring-inset focus:ring-accent/30"
              autoComplete="off"
              autoFocus
            />
            {filtered.length === 0 ? (
              <div
                id="comparable-ticker-listbox"
                role="status"
                className="text-xs text-ink-mute px-3 py-4 text-center"
              >
                No matches
              </div>
            ) : (
              <div
                id="comparable-ticker-listbox"
                role="listbox"
                aria-label="Comparable tickers"
                className="max-h-52 overflow-y-auto py-1"
              >
                {filtered.map((t) => {
                  const on = selected.includes(t);
                  const disabled = !on && atCap;
                  return (
                    <button
                      key={t}
                      type="button"
                      role="option"
                      aria-selected={on ? 'true' : 'false'}
                      disabled={disabled}
                      onClick={() => {
                        if (on) onRemove(t);
                        else if (!atCap) {
                          onAdd(t);
                          setOpen(false);
                        }
                      }}
                      className={`w-full text-left px-3 py-1.5 text-xs font-mono transition-colors ${
                        on
                          ? 'bg-accent/15 text-accent'
                          : disabled
                            ? 'text-ink-mute opacity-40 cursor-not-allowed'
                            : 'text-ink-soft hover:bg-ink/[0.06] hover:text-ink'
                      }`}
                    >
                      {t}
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </div>

      {loading && <span className="text-[11px] text-ink-mute" aria-hidden="true">&nbsp;</span>}
      {error && !open && <span className="text-[11px] text-down/90 max-w-[220px] truncate" title={error}>{error}</span>}
    </div>
  );
}

function DailyReturnsComboChart({ snaps }: { snaps: NavChartPoint[] }) {
  const { containerRef, chart, colors, isAlive } = useLightweightChart({
    leftPriceScale: { visible: true },
  });
  const tip = useChartTip(chart, containerRef, isAlive);
  const barsRef = useRef<ISeriesApi<'Histogram'> | null>(null);
  const navRef = useRef<ISeriesApi<'Line'> | null>(null);

  const data = useMemo(() => buildDailyReturnsWithNavIndex(snaps), [snaps]);
  const byDate = useMemo(() => new Map(data.map((d) => [d.date, d])), [data]);

  useEffect(() => {
    if (!chart || data.length < 2) return;
    const bars = chart.addSeries(HistogramSeries, {
      priceScaleId: 'left',
      priceLineVisible: false,
      lastValueVisible: false,
      priceFormat: { type: 'custom', formatter: (v: number) => `${v.toFixed(1)}%`, minMove: 0.01 },
    });
    const nav = chart.addSeries(LineSeries, {
      lineWidth: 2,
      priceScaleId: 'right',
      priceLineVisible: false,
      lastValueVisible: false,
      priceFormat: { type: 'custom', formatter: (v: number) => v.toFixed(2), minMove: 0.01 },
    });
    nav.setData(toLineData(data, (d) => d.date, (d) => d.navIndex));
    barsRef.current = bars;
    navRef.current = nav;
    chart.timeScale().fitContent();
    return () => {
      barsRef.current = null;
      navRef.current = null;
      if (isAlive()) {
        chart.removeSeries(bars);
        chart.removeSeries(nav);
      }
    };
  }, [chart, data, isAlive]);

  // Per-bar up/down colors + NAV accent — reset on theme flips.
  useEffect(() => {
    barsRef.current?.setData(
      data.map((d) =>
        d.dailyPct == null
          ? { time: d.date as Time }
          : {
              time: d.date as Time,
              value: d.dailyPct,
              color: d.dailyPct >= 0 ? withAlpha(colors.up, 0.75) : withAlpha(colors.down, 0.75),
            }
      )
    );
    navRef.current?.applyOptions({ color: colors.accent });
  }, [colors, data]);

  if (data.length < 2) {
    return (
      <div className="h-full min-h-[280px] flex items-center justify-center text-ink-mute text-sm">
        Need at least two NAV points in this range.
      </div>
    );
  }

  const tipRow = tip ? byDate.get(tip.iso) : undefined;

  return (
    <div className="h-full w-full flex flex-col gap-1.5">
      <div className="flex flex-wrap justify-end gap-x-4 gap-y-1 text-[11px] text-ink-soft pr-1">
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-flex gap-0.5 shrink-0" aria-hidden>
            <span className="w-2.5 h-2.5 rounded-sm bg-up/75" />
            <span className="w-2.5 h-2.5 rounded-sm bg-down/75" />
          </span>
          Daily return %
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="w-3 h-0.5 rounded-full bg-accent shrink-0" aria-hidden />
          NAV (indexed)
        </span>
      </div>
      <div ref={containerRef} className="relative flex-1 min-h-0">
        {tip && tipRow ? (
          <ChartTipShell tip={tip}>
            <p className="text-ink-soft text-[0.75rem] font-mono">{tip.iso}</p>
            <div className="flex justify-between gap-3 mt-0.5">
              <span className="text-ink-soft">Daily return</span>
              <span
                className="font-mono tabular-nums"
                style={{ color: tipRow.dailyPct == null ? colors.inkSoft : tipRow.dailyPct >= 0 ? colors.up : colors.down }}
              >
                {tipRow.dailyPct != null ? `${tipRow.dailyPct >= 0 ? '+' : ''}${tipRow.dailyPct.toFixed(2)}%` : '—'}
              </span>
            </div>
            <div className="flex justify-between gap-3">
              <span className="text-ink-soft">NAV (indexed)</span>
              <span className="font-mono tabular-nums text-ink">{tipRow.navIndex.toFixed(2)}</span>
            </div>
          </ChartTipShell>
        ) : null}
      </div>
    </div>
  );
}

const MAX_COMPARABLES = 8;

export function PerformanceChartWorkspace({
  view,
  onViewChange,
  chartData,
  selectedComparables,
  onAddComparable,
  onRemoveComparable,
  tickerUniverse,
  comparableLoading,
  comparableError,
  snaps,
  drawdownData,
  rollingData,
  rollingWindow,
  activityMarkerDates,
  activityEventsByDate,
}: {
  view: PerformanceChartView;
  onViewChange: (v: PerformanceChartView) => void;
  chartData: PerfChartPoint[];
  selectedComparables: string[];
  onAddComparable: (ticker: string) => void;
  onRemoveComparable: (ticker: string) => void;
  tickerUniverse: string[];
  comparableLoading: boolean;
  comparableError: string | null;
  snaps: NavChartPoint[];
  drawdownData: Array<{ date: string; drawdown: number }>;
  rollingData: Array<{ date: string; sharpe: number | null; volAnn: number | null }>;
  rollingWindow: number;
  activityMarkerDates?: string[];
  activityEventsByDate?: Record<string, { ticker: string; event: string }[]>;
}) {
  return (
    <div className="glass-card p-0 overflow-hidden">
      <div className="p-4 border-b border-hair bg-term-bg/60 space-y-3">
        <div className="flex flex-col gap-2">
          <span className="text-[10px] text-ink-mute uppercase tracking-wider">Chart</span>
          <div className="flex flex-wrap gap-2">
            {VIEW_OPTIONS.map((opt) => (
              <button
                key={opt.id}
                type="button"
                onClick={() => onViewChange(opt.id)}
                title={opt.hint}
                className={`text-left px-3 py-2 rounded-lg text-xs font-medium border transition-colors max-w-[200px] ${
                  view === opt.id
                    ? 'border-accent bg-accent/15 text-accent'
                    : 'border-hair text-ink-soft hover:bg-ink/[0.04] hover:text-ink'
                }`}
              >
                <span className="block">{opt.label}</span>
              </button>
            ))}
          </div>
        </div>

        {view === 'nav' && (
          <div className="pt-2 border-t border-hair/80">
            <ComparableDropdown
              universe={tickerUniverse}
              selected={selectedComparables}
              maxComparables={MAX_COMPARABLES}
              onAdd={onAddComparable}
              onRemove={onRemoveComparable}
              loading={comparableLoading}
              error={comparableError}
            />
          </div>
        )}
      </div>

      <div className="p-4">
        {view === 'nav' && (
          <div className="space-y-2">
            <div className="h-[min(520px,58vh)] min-h-[360px] w-full">
              <NavComparableChart
                data={chartData}
                comparableKeys={selectedComparables}
                onLegendRemoveComparable={onRemoveComparable}
                activityMarkerDates={activityMarkerDates}
                activityEventsByDate={activityEventsByDate}
              />
            </div>
          </div>
        )}

        {view === 'daily_returns' && (
          <div className="h-[min(520px,58vh)] min-h-[360px] w-full">
            <DailyReturnsComboChart snaps={snaps} />
          </div>
        )}

        {view === 'drawdown' && (
          <div className="h-[min(520px,58vh)] min-h-[360px] w-full">
            <PerformanceDrawdownChart data={drawdownData} />
          </div>
        )}

        {view === 'rolling' && (
          <PerformanceRollingChart data={rollingData} snaps={snaps} rollingWindow={rollingWindow} />
        )}
      </div>
    </div>
  );
}
