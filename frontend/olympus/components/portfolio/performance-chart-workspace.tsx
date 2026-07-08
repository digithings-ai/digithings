'use client';

import { useMemo, useState, useRef, useEffect, type ComponentProps } from 'react';
import { ChevronDown } from 'lucide-react';
import {
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  Area,
  ComposedChart,
  Line,
  Bar,
  Cell,
  ReferenceLine,
} from 'recharts';
import type { NavChartPoint, PerfChartPoint } from '@/lib/types';
import { PerformanceDrawdownChart } from '@/components/portfolio/performance-drawdown-chart';
import { PerformanceRollingChart } from '@/components/portfolio/performance-rolling-chart';
import type { PerformanceChartView } from '@/lib/performance-series';
import { buildDailyReturnsWithNavIndex } from '@/lib/performance-series';
import { BENCHMARK_COLORS, EVENT_COLORS, useChartColors, withAlpha } from '@/lib/chart-colors';

// Benchmark hues live in the sanctioned fixed allowlist (lib/chart-colors.ts).
function lineColorForTicker(t: string): string {
  if (BENCHMARK_COLORS[t]) return BENCHMARK_COLORS[t];
  let h = 0;
  for (let i = 0; i < t.length; i++) {
    h = t.charCodeAt(i) + ((h << 5) - h);
  }
  const hue = Math.abs(h) % 360;
  return `hsl(${hue} 62% 58%)`;
}

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

type LegendPayloadItem = {
  value?: string;
  dataKey?: string | number;
  color?: string;
};

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
  /** Dates in range with OPEN/EXIT/TRIM/ADD — vertical guides on the NAV chart. */
  activityMarkerDates?: string[];
  /** Pre-aggregated events per date for tooltip enrichment. */
  activityEventsByDate?: Record<string, { ticker: string; event: string }[]>;
}) {
  const chart = useChartColors();
  if (data.length < 2) {
    return (
      <div className="h-full min-h-[280px] flex items-center justify-center text-ink-mute text-sm">
        Need at least two NAV points in this range.
      </div>
    );
  }

  const legendContent = (props: { payload?: LegendPayloadItem[] }) => {
    const { payload } = props;
    if (!payload?.length) return null;
    return (
      <div className="flex flex-wrap justify-end gap-x-4 gap-y-1 w-full pr-1">
        {payload.map((item) => {
          const key = String(item.dataKey ?? item.value ?? '');
          if (key === 'portfolio') {
            return (
              <span
                key="portfolio"
                className="inline-flex items-center gap-1.5 text-[11px] text-ink-mute shrink-0"
              >
                <span className="w-2.5 h-2.5 rounded-sm bg-accent/90 shrink-0" />
                Portfolio
              </span>
            );
          }
          if (!comparableKeys.includes(key)) return null;
          const stroke = item.color ?? lineColorForTicker(key);
          return (
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
                  stroke={stroke}
                  strokeWidth={2}
                  strokeDasharray="4 3"
                />
              </svg>
              {item.value ?? key}
            </button>
          );
        })}
      </div>
    );
  };

  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
        <CartesianGrid stroke={chart.hair} />
        <XAxis
          dataKey="date"
          tick={{ fill: chart.axis, fontSize: 11 }}
          tickFormatter={(d: string) => d?.slice(5)}
        />
        <YAxis
          tick={{ fill: chart.axis, fontSize: 11 }}
          domain={['auto', 'auto']}
          label={{
            value: 'Indexed (100 = window start)',
            angle: -90,
            position: 'insideLeft',
            fill: chart.axis,
            fontSize: 10,
          }}
        />
        <Tooltip
          content={({ active, payload, label }) => {
            if (!active || !payload?.length) return null;
            const events = activityEventsByDate?.[String(label)] ?? [];
            return (
              <div
                style={{
                  background: 'var(--term-bg)',
                  border: '1px solid var(--hair)',
                  borderRadius: '8px',
                  fontSize: '0.82rem',
                  padding: '8px 12px',
                  maxWidth: 220,
                }}
              >
                <p style={{ color: 'var(--ink-soft)', marginBottom: 4, fontSize: '0.75rem' }}>
                  {String(label)}
                </p>
                {payload.map((item) => (
                  <div key={String(item.dataKey)} style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
                    <span style={{ color: item.color ?? 'var(--ink-soft)' }}>{String(item.name ?? item.dataKey)}</span>
                    <span style={{ fontFamily: 'monospace', color: 'var(--ink)' }}>
                      {item.value != null && !Number.isNaN(Number(item.value))
                        ? Number(item.value).toFixed(2)
                        : '—'}
                    </span>
                  </div>
                ))}
                {events.length > 0 && (
                  <div style={{ marginTop: 6, paddingTop: 6, borderTop: '1px solid var(--hair)' }}>
                    {events.map((ev, i) => (
                      <div key={i} style={{ color: 'var(--ink-soft)', fontSize: '0.72rem', display: 'flex', gap: 6 }}>
                        <span
                          style={{
                            color:
                              ev.event === 'OPEN'
                                ? EVENT_COLORS.OPEN
                                : ev.event === 'EXIT'
                                  ? EVENT_COLORS.EXIT
                                  : ev.event === 'ADD'
                                    ? EVENT_COLORS.ADD
                                    : ev.event === 'TRIM'
                                      ? EVENT_COLORS.TRIM
                                      : 'var(--ink-soft)',
                          }}
                        >
                          {ev.event}
                        </span>
                        <span style={{ fontFamily: 'monospace' }}>{ev.ticker}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          }}
        />
        {(activityMarkerDates ?? []).map((d) => (
          <ReferenceLine
            key={d}
            x={d}
            stroke={withAlpha(chart.ink, 0.14)}
            strokeDasharray="4 5"
          />
        ))}
        <Legend
          verticalAlign="top"
          align="right"
          content={legendContent as ComponentProps<typeof Legend>['content']}
          wrapperStyle={{ top: 0, width: '100%' }}
        />
        <Area
          type="monotone"
          dataKey="portfolio"
          name="Portfolio NAV"
          stroke={chart.accent}
          fill={withAlpha(chart.accent, 0.12)}
          strokeWidth={2}
          dot={false}
          connectNulls
        />
        {comparableKeys.map((b) => (
          <Line
            key={b}
            type="monotone"
            dataKey={b}
            name={b}
            stroke={lineColorForTicker(b)}
            strokeDasharray="4 4"
            strokeWidth={1.5}
            dot={false}
            connectNulls
          />
        ))}
      </ComposedChart>
    </ResponsiveContainer>
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
            className="p-0.5 rounded hover:bg-white/10 text-ink-soft hover:text-ink leading-none"
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
                            : 'text-ink-soft hover:bg-white/[0.06] hover:text-ink'
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
  const chart = useChartColors();
  const data = buildDailyReturnsWithNavIndex(snaps);
  if (data.length < 2) {
    return (
      <div className="h-full min-h-[280px] flex items-center justify-center text-ink-mute text-sm">
        Need at least two NAV points in this range.
      </div>
    );
  }
  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={data} margin={{ top: 8, right: 16, left: 4, bottom: 0 }}>
        <CartesianGrid stroke={chart.hair} />
        <XAxis
          dataKey="date"
          tick={{ fill: chart.axis, fontSize: 11 }}
          tickFormatter={(d: string) => d?.slice(5)}
        />
        <YAxis
          yAxisId="left"
          tick={{ fill: chart.axis, fontSize: 11 }}
          tickFormatter={(v) => `${v}%`}
          label={{ value: 'Daily %', angle: -90, position: 'insideLeft', fill: chart.axis, fontSize: 10 }}
        />
        <YAxis
          yAxisId="right"
          orientation="right"
          tick={{ fill: chart.axis, fontSize: 11 }}
          domain={['auto', 'auto']}
          label={{
            value: 'NAV index',
            angle: 90,
            position: 'insideRight',
            fill: chart.axis,
            fontSize: 10,
          }}
        />
        <Tooltip
          contentStyle={{
            background: 'var(--term-bg)',
            border: '1px solid var(--hair)',
            color: 'var(--ink)',
            borderRadius: '8px',
            fontSize: '0.85rem',
          }}
        />
        <Legend />
        <Bar yAxisId="left" dataKey="dailyPct" name="Daily return %" maxBarSize={16} radius={[2, 2, 0, 0]}>
          {data.map((entry, i) => (
            <Cell
              key={i}
              fill={
                entry.dailyPct == null
                  ? withAlpha(chart.axis, 0.45)
                  : entry.dailyPct >= 0
                    ? withAlpha(chart.up, 0.75)
                    : withAlpha(chart.down, 0.75)
              }
            />
          ))}
        </Bar>
        <Line
          yAxisId="right"
          type="monotone"
          dataKey="navIndex"
          name="NAV (indexed)"
          stroke={chart.accent}
          strokeWidth={2}
          dot={false}
          connectNulls
        />
      </ComposedChart>
    </ResponsiveContainer>
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
                    : 'border-hair text-ink-soft hover:bg-white/[0.04] hover:text-ink'
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
