'use client';

import { useMemo, useState, useCallback, useEffect } from 'react';
import { useSearchParams, useRouter, usePathname } from 'next/navigation';
import { useDashboard } from '@/lib/dashboard-context';
import { formatPct } from '@/components/ui';
import { ChevronDown, ChevronUp } from 'lucide-react';
import type { BenchmarkHistoryMap, NavChartPoint, PerfChartPoint, Thesis } from '@/lib/types';
import {
  PerformanceDashboard,
  type DashboardAllocation,
  type DashboardHeadline,
  type DashboardRatio,
} from '@digithings/web';
import { PositionPnlTable } from '@/components/portfolio/position-pnl-table';
import { AdvancedStatsPanel } from '@/components/portfolio/advanced-stats-panel';
import { PerformanceDateRange } from '@/components/portfolio/performance-date-range';
import { PerformanceChartWorkspace } from '@/components/portfolio/performance-chart-workspace';
import { buildSleeveStackSeries, categoryStackLabel } from '@/lib/portfolio-aggregates';
import PageSkeleton from '@/components/page-skeleton';
import { fetchComparablePriceHistory } from '@/lib/queries';
import {
  filterByDateRange,
  parseDateRangeKey,
  parseChartViewKey,
  buildDrawdownSeries,
  buildRollingSharpeVol,
  computeEffectiveRollingWindow,
  type DateRangeKey,
  type PerformanceChartView,
} from '@/lib/performance-series';
import { computeEffectivePortfolioRiskMetrics } from '@/lib/portfolio-risk-metrics';

const MAX_COMPARABLES = 8;

function fmtNav(v: number | null | undefined): string {
  if (v == null) return '—';
  return v.toFixed(2);
}

function dayReturn(snaps: NavChartPoint[]): number | null {
  if (!snaps || snaps.length < 2) return null;
  const prev = snaps[snaps.length - 2].nav;
  const curr = snaps[snaps.length - 1].nav;
  if (!prev) return null;
  return ((curr - prev) / prev) * 100;
}

function periodReturnPct(snaps: NavChartPoint[]): number | null {
  if (!snaps || snaps.length < 2) return null;
  const first = snaps[0].nav;
  const last = snaps[snaps.length - 1].nav;
  if (!first || first <= 0) return null;
  return (last / first - 1) * 100;
}

/** Portfolio tab: full performance workspace (embedded under shared Portfolio shell). */
export default function PerformanceTab() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const range = parseDateRangeKey(searchParams.get('range'));
  const view = parseChartViewKey(searchParams.get('view'));

  const setRange = useCallback(
    (k: DateRangeKey) => {
      const p = new URLSearchParams(searchParams.toString());
      p.set('tab', 'performance');
      p.set('range', k);
      router.replace(`${pathname}?${p.toString()}`, { scroll: false });
    },
    [pathname, router, searchParams]
  );

  const setView = useCallback(
    (v: PerformanceChartView) => {
      const p = new URLSearchParams(searchParams.toString());
      p.set('tab', 'performance');
      p.set('view', v);
      router.replace(`${pathname}?${p.toString()}`, { scroll: false });
    },
    [pathname, router, searchParams]
  );

  const { data, loading, error } = useDashboard();
  const lastUpdated = data?.portfolio?.meta?.last_updated ?? null;
  const [comparableOverride, setComparableOverride] = useState<string[] | null>(null);
  const [showAdvanced, setShowAdvanced] = useState(true);
  const [comparableHistory, setComparableHistory] = useState<BenchmarkHistoryMap>({});
  const [comparableLoading, setComparableLoading] = useState(false);
  const [comparableError, setComparableError] = useState<string | null>(null);

  const positions = useMemo(() => data?.positions ?? [], [data]);
  const position_events = useMemo(() => data?.position_events ?? [], [data]);
  const positionHistory = useMemo(() => data?.position_history ?? [], [data]);
  const benchmarks = useMemo(() => data?.benchmarks ?? {}, [data]);
  const metrics = data?.calculated;
  const serverMetrics = data?.server_portfolio_metrics ?? null;
  const allSnaps = useMemo(() => data?.portfolio?.snapshots ?? [], [data]);
  const tickerUniverse = useMemo(() => data?.price_history_tickers ?? [], [data]);
  const theses = useMemo(() => data?.portfolio?.strategy?.theses ?? [], [data]);
  const thesisById = useMemo(() => new Map<string, Thesis>(theses.map((t) => [t.id, t])), [theses]);

  const snaps = useMemo(() => filterByDateRange(allSnaps, range), [allSnaps, range]);

  /** Dates in the selected range that have non-HOLD position events — NAV chart guides. */
  const activityMarkerDates = useMemo(() => {
    if (!snaps.length) return [];
    const minD = snaps[0].date;
    const maxD = snaps[snaps.length - 1].date;
    const set = new Set<string>();
    for (const ev of position_events) {
      if (ev.event === 'HOLD') continue;
      if (ev.date >= minD && ev.date <= maxD) set.add(ev.date);
    }
    return [...set].sort().slice(-18);
  }, [position_events, snaps]);

  /** Pre-aggregated events by date for NAV chart tooltip (date → [{ticker, event}]). */
  const activityEventsByDate = useMemo<Record<string, { ticker: string; event: string }[]>>(() => {
    const map: Record<string, { ticker: string; event: string }[]> = {};
    for (const d of activityMarkerDates) {
      map[d] = position_events
        .filter((ev) => ev.date === d && ev.event !== 'HOLD')
        .map((ev) => ({ ticker: ev.ticker, event: ev.event }));
    }
    return map;
  }, [activityMarkerDates, position_events]);

  const defaultComparableSelection = useMemo(() => {
    if (!tickerUniverse.length) return [];
    if (tickerUniverse.includes('SPY')) return ['SPY'];
    return [tickerUniverse[0]];
  }, [tickerUniverse]);

  const selectedComparables = comparableOverride ?? defaultComparableSelection;
  const comparableKey = selectedComparables.join('|');

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!snaps.length || selectedComparables.length === 0) {
        if (!cancelled) {
          setComparableHistory({});
          setComparableLoading(false);
          setComparableError(null);
        }
        return;
      }
      const minD = snaps[0].date;
      const maxD = snaps[snaps.length - 1].date;
      setComparableLoading(true);
      setComparableError(null);
      try {
        const map = await fetchComparablePriceHistory(selectedComparables, minD, maxD);
        if (cancelled) return;
        setComparableHistory(map);
        const sparse = selectedComparables.filter((b) => (map[b]?.history?.length ?? 0) < 2);
        if (sparse.length) {
          setComparableError(
            `Not enough history in this range for: ${sparse.join(', ')}. Try a wider date range or different tickers.`
          );
        } else {
          setComparableError(null);
        }
      } catch (e) {
        if (!cancelled) {
          setComparableHistory({});
          setComparableError(e instanceof Error ? e.message : 'Failed to load comparables');
        }
      } finally {
        if (!cancelled) setComparableLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [snaps, comparableKey, selectedComparables]);

  const latestNav = snaps.length ? snaps[snaps.length - 1].nav : 100;
  const dailyRet = dayReturn(snaps);
  const rangeReturn = periodReturnPct(snaps);

  const chartData = useMemo<PerfChartPoint[]>(() => {
    const snapMap: Record<string, number | null> = {};
    snaps.forEach((s) => {
      snapMap[s.date] = s.nav;
    });

    const inceptionDate = snaps.length ? snaps[0].date : null;
    if (!inceptionDate) return [];

    const firstNav = snaps[0].nav;
    const dateSet = new Set(snaps.map((s) => s.date));

    selectedComparables.forEach((b) => {
      (comparableHistory[b]?.history || [])
        .filter((h) => h.date >= inceptionDate)
        .forEach((h) => dateSet.add(h.date));
    });

    const allDates = [...dateSet].filter((d) => d >= inceptionDate).sort();

    const bases: Record<string, number> = {};
    selectedComparables.forEach((b) => {
      const hist = (comparableHistory[b]?.history || []).filter((h) => h.date >= inceptionDate);
      if (hist.length) bases[b] = hist[0].price;
    });

    const benchMaps: Record<string, Record<string, number>> = {};
    selectedComparables.forEach((b) => {
      const m: Record<string, number> = {};
      (comparableHistory[b]?.history || [])
        .filter((h) => h.date >= inceptionDate)
        .forEach((h) => {
          m[h.date] = h.price;
        });
      benchMaps[b] = m;
    });

    return allDates.map((d) => {
      const rawNav = snapMap[d];
      const row: PerfChartPoint = {
        date: d,
        portfolio:
          rawNav != null && firstNav > 0 ? +((rawNav / firstNav) * 100).toFixed(2) : null,
      };
      selectedComparables.forEach((b) => {
        const p = benchMaps[b]?.[d];
        row[b] = p != null && bases[b] ? +((p / bases[b]) * 100).toFixed(2) : null;
      });
      return row;
    });
  }, [snaps, comparableHistory, selectedComparables]);

  const drawdownData = useMemo(() => buildDrawdownSeries(snaps), [snaps]);
  const rollingWindow = useMemo(() => computeEffectiveRollingWindow(snaps.length, 21), [snaps.length]);
  const rollingData = useMemo(() => buildRollingSharpeVol(snaps, 21), [snaps]);
  const effectiveRiskMetrics = useMemo(
    () => computeEffectivePortfolioRiskMetrics(serverMetrics, snaps),
    [serverMetrics, snaps]
  );

  /** Server-metrics reads on the canonical <PerformanceDashboard/> grammar
   * (#1548, replaces the inline strip). Tone only on signed money reads:
   * P&L headline and a negative max drawdown; ratios stay ink. The strip's
   * "Server metrics · date · generated" caption folds into the headline
   * label + note. (Wiring: the dashboard's pdash-* hairlines + utilities
   * need globals.css to `@import "@digithings/web/styles/finance-composites.css"`
   * and `@source "../../digiweb/web/src/components/finance-composites";`.) */
  const serverDashboard = useMemo<{
    headlines: DashboardHeadline[];
    ratios: DashboardRatio[];
  } | null>(() => {
    if (!serverMetrics) return null;
    const m = serverMetrics;
    const r = effectiveRiskMetrics;
    const noteParts: string[] = [];
    const asOf = m.as_of_date ?? m.date ?? null;
    if (asOf) noteParts.push(`as of ${asOf}`);
    if (m.generated_at) noteParts.push(`generated ${m.generated_at.slice(0, 19)}`);
    const headlines: DashboardHeadline[] = [
      {
        label: 'server p&l',
        value:
          m.pnl_pct != null ? `${m.pnl_pct >= 0 ? '+' : ''}${m.pnl_pct.toFixed(2)}%` : '—',
        tone: m.pnl_pct != null ? (m.pnl_pct >= 0 ? 'up' : 'down') : undefined,
        note: noteParts.length ? noteParts.join(' · ') : undefined,
      },
    ];
    const ratios: DashboardRatio[] = [
      { label: 'sharpe', value: r.sharpe != null ? r.sharpe.toFixed(2) : '—' },
      { label: 'ann. vol', value: r.annVolPct != null ? `${r.annVolPct.toFixed(2)}%` : '—' },
      {
        label: 'max drawdown',
        value: r.maxDrawdownPct != null ? `${r.maxDrawdownPct.toFixed(2)}%` : '—',
        tone: r.maxDrawdownPct != null && r.maxDrawdownPct < 0 ? 'down' : undefined,
      },
      { label: 'cash', value: m.cash_pct != null ? `${m.cash_pct.toFixed(1)}%` : '—' },
      {
        label: 'invested',
        value: m.invested_pct != null ? `${m.invested_pct.toFixed(1)}%` : '—',
      },
    ];
    return { headlines, ratios };
  }, [serverMetrics, effectiveRiskMetrics]);

  /** Current sleeve mix for the dashboard's allocation bars — the same
   * category aggregation AllocationsTab stacks, sliced at the latest date
   * (position_history is already on the dashboard payload; no new fetch). */
  const sleeveAllocations = useMemo<DashboardAllocation[]>(() => {
    const { data: series, keys } = buildSleeveStackSeries(positionHistory, 'category');
    const latest = series[series.length - 1];
    if (!latest) return [];
    return keys
      .map((k) => {
        const w = latest[k];
        return {
          name: categoryStackLabel(k),
          pct: typeof w === 'number' ? Math.round(w * 10) / 10 : 0,
        };
      })
      .filter((a) => a.pct > 0)
      .sort((a, b) => b.pct - a.pct);
  }, [positionHistory]);

  const onAddComparable = useCallback(
    (t: string) => {
      const u = String(t).toUpperCase().trim();
      if (!u) return;
      setComparableOverride((prev) => {
        const cur = prev ?? defaultComparableSelection;
        if (cur.includes(u) || cur.length >= MAX_COMPARABLES) return cur;
        return [...cur, u];
      });
    },
    [defaultComparableSelection]
  );

  const onRemoveComparable = useCallback(
    (t: string) => {
      setComparableOverride((prev) => {
        const cur = prev ?? defaultComparableSelection;
        return cur.filter((x) => x !== t);
      });
    },
    [defaultComparableSelection]
  );

  // bare: rendered inside the portfolio shell's container (#1548)
  if (loading) return <PageSkeleton bare />;
  if (error || !data || !metrics)
    return (
      <div className="flex items-center justify-center min-h-[40vh] text-down">
        {error || 'Failed to load'}
      </div>
    );

  const priceChartAnchorDate =
    snaps.length > 0 ? snaps[snaps.length - 1].date : (data.portfolio.meta.last_updated ?? null);

  const totalReturnLabel = range === 'itd' ? 'Since inception' : 'Selected range';
  const displayedReturn = range === 'itd' ? metrics.portfolio_pnl : rangeReturn;
  const totalReturnValue = formatPct(displayedReturn);
  const overviewHeadlines: DashboardHeadline[] = [
    {
      label: 'portfolio NAV',
      value: fmtNav(latestNav),
      note: 'end of range · level',
    },
    {
      label: 'total return',
      value: totalReturnValue,
      tone: displayedReturn == null ? undefined : displayedReturn >= 0 ? 'up' : 'down',
      note: totalReturnLabel.toLowerCase(),
    },
  ];
  const overviewRatios: DashboardRatio[] = [
    {
      label: 'daily P&L',
      value: dailyRet != null ? formatPct(dailyRet) : '—',
      tone: dailyRet == null ? undefined : dailyRet >= 0 ? 'up' : 'down',
    },
    { label: 'active positions', value: String(positions.length) },
    {
      label: 'invested',
      value:
        serverMetrics?.invested_pct != null ? `${serverMetrics.invested_pct.toFixed(1)}%` : '—',
    },
    {
      label: 'cash',
      value: serverMetrics?.cash_pct != null ? `${serverMetrics.cash_pct.toFixed(1)}%` : '—',
    },
  ];

  return (
    <div className="space-y-10">
      <section className="space-y-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div className="min-w-0 space-y-1">
            <p className="text-[11px] font-semibold text-ink-mute tracking-wide">
              Summary
              {lastUpdated ? <span className="font-mono font-normal"> · as of {lastUpdated}</span> : null}
            </p>
            {/* Performance summary sentence */}
            {snaps.length >= 2 && (
              <p className="text-sm text-ink-soft">
                Portfolio{' '}
                <span className={displayedReturn != null ? (displayedReturn >= 0 ? 'text-up font-semibold' : 'text-down font-semibold') : ''}>
                  {displayedReturn != null ? (displayedReturn >= 0 ? `+${displayedReturn.toFixed(2)}%` : `${displayedReturn.toFixed(2)}%`) : '—'}
                </span>
                {' '}{range === 'itd' ? 'since inception' : 'over the selected range'}{dailyRet != null && (
                  <>, <span className={dailyRet >= 0 ? 'text-up font-semibold' : 'text-down font-semibold'}>{dailyRet >= 0 ? '+' : ''}{dailyRet.toFixed(2)}%</span> today</>)
                }.
              </p>
            )}
          </div>
          <div className="shrink-0">
            <PerformanceDateRange value={range} onChange={setRange} />
          </div>
        </div>

        <PerformanceDashboard
          headlines={overviewHeadlines}
          ratios={overviewRatios}
          ratioColumns={4}
        >
          <PerformanceChartWorkspace
            embedded
            view={view}
            onViewChange={setView}
            chartData={chartData}
            selectedComparables={selectedComparables}
            onAddComparable={onAddComparable}
            onRemoveComparable={onRemoveComparable}
            tickerUniverse={tickerUniverse}
            comparableLoading={comparableLoading}
            comparableError={comparableError}
            snaps={snaps}
            drawdownData={drawdownData}
            rollingData={rollingData}
            rollingWindow={rollingWindow}
            activityMarkerDates={activityMarkerDates}
            activityEventsByDate={activityEventsByDate}
          />
        </PerformanceDashboard>
      </section>

      <section className="space-y-3">
        <p className="text-[11px] font-semibold text-ink-mute tracking-wide">Positions</p>
        <PositionPnlTable
          key={`${priceChartAnchorDate ?? 'no-anchor'}|${snaps[0]?.date ?? ''}`}
          positions={positions}
          priceChartAnchorDate={priceChartAnchorDate}
          positionHistory={positionHistory}
          positionEvents={position_events}
          navWindowStart={snaps.length ? snaps[0].date : null}
          thesisById={thesisById}
        />
      </section>

      <section className="space-y-3">
        <p className="text-[11px] font-semibold text-ink-mute tracking-wide">Diagnostics</p>
        <div className="glass-card overflow-hidden">
          <button
            type="button"
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="w-full flex items-center justify-between px-6 py-4 hover:bg-ink/[0.02] transition-colors"
          >
            <h3 className="text-lg font-semibold">Advanced statistics</h3>
            {showAdvanced ? (
              <ChevronUp size={18} className="text-ink-mute" />
            ) : (
              <ChevronDown size={18} className="text-ink-mute" />
            )}
          </button>
          {showAdvanced && serverDashboard && (
            <PerformanceDashboard
              className="mx-6 mb-6"
              headlines={serverDashboard.headlines}
              ratios={serverDashboard.ratios}
              ratioColumns={5}
              allocations={sleeveAllocations.length > 0 ? sleeveAllocations : undefined}
              allocationsLabel="allocation by sleeve"
            />
          )}
          {showAdvanced && (
            <AdvancedStatsPanel
              snaps={snaps}
              benchmarks={benchmarks}
              serverMetrics={serverMetrics}
            />
          )}
        </div>
      </section>
    </div>
  );
}
