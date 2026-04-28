'use client';

import { useMemo, useState, useCallback, useEffect } from 'react';
import { useSearchParams, useRouter, usePathname } from 'next/navigation';
import { useDashboard } from '@/lib/dashboard-context';
import { StatCard, formatPct, pnlColor } from '@/components/ui';
import { TrendingUp, BarChart3, Activity, Target, ChevronDown, ChevronUp } from 'lucide-react';
import type { BenchmarkHistoryMap, NavChartPoint, PerfChartPoint, Thesis } from '@/lib/types';
import { PositionPnlTable } from '@/components/portfolio/position-pnl-table';
import { AdvancedStatsPanel } from '@/components/portfolio/advanced-stats-panel';
import { PerformanceDateRange } from '@/components/portfolio/performance-date-range';
import { ServerMetricsStrip } from '@/components/portfolio/server-metrics-strip';
import { PerformanceChartWorkspace } from '@/components/portfolio/performance-chart-workspace';
import AtlasLoader from '@/components/AtlasLoader';
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
    // eslint-disable-next-line react-hooks/exhaustive-deps -- comparableKey encodes selectedComparables
  }, [snaps, comparableKey]);

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

  if (loading) return <AtlasLoader fullScreen={false} />;
  if (error || !data || !metrics)
    return (
      <div className="flex items-center justify-center min-h-[40vh] text-fin-red">
        {error || 'Failed to load'}
      </div>
    );

  const priceChartAnchorDate =
    snaps.length > 0 ? snaps[snaps.length - 1].date : (data.portfolio.meta.last_updated ?? null);

  const totalReturnLabel = range === 'itd' ? 'Since inception' : 'Selected range';
  const totalReturnValue =
    range === 'itd' ? formatPct(metrics.portfolio_pnl) : formatPct(rangeReturn);

  return (
    <div className="space-y-10">
      <section className="space-y-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div className="min-w-0 space-y-1">
            <p className="text-[11px] font-semibold text-text-muted tracking-wide">Summary</p>
            {/* Performance summary sentence */}
            {snaps.length >= 2 && (
              <p className="text-sm text-text-secondary">
                Portfolio{' '}
                <span className={rangeReturn != null ? (rangeReturn >= 0 ? 'text-fin-green font-semibold' : 'text-fin-red font-semibold') : ''}>
                  {rangeReturn != null ? (rangeReturn >= 0 ? `+${rangeReturn.toFixed(2)}%` : `${rangeReturn.toFixed(2)}%`) : formatPct(metrics.portfolio_pnl)}
                </span>
                {' '}since inception{dailyRet != null && (
                  <>, <span className={dailyRet >= 0 ? 'text-fin-green font-semibold' : 'text-fin-red font-semibold'}>{dailyRet >= 0 ? '+' : ''}{dailyRet.toFixed(2)}%</span> today</>)
                }.
              </p>
            )}
          </div>
          <div className="shrink-0">
            <PerformanceDateRange value={range} onChange={setRange} />
          </div>
        </div>

        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard
            label="Portfolio NAV"
            value={fmtNav(latestNav)}
            icon={TrendingUp}
            iconColor="text-fin-blue"
            subtitle="End of range (level)"
          />
          <StatCard
            label="Total Return"
            value={totalReturnValue}
            valueClass={pnlColor(range === 'itd' ? metrics.portfolio_pnl : rangeReturn)}
            icon={BarChart3}
            iconColor="text-fin-green"
            subtitle={totalReturnLabel}
          />
          <StatCard
            label="Daily P&L"
            value={dailyRet != null ? formatPct(dailyRet) : '—'}
            valueClass={pnlColor(dailyRet)}
            icon={Activity}
            iconColor="text-fin-amber"
            subtitle={
              dailyRet == null
                ? 'Not enough data in range'
                : 'Last day in range'
            }
          />
          <StatCard
            label="Active Positions"
            value={positions.length}
            icon={Target}
            iconColor="text-fin-purple"
          />
        </div>
      </section>

      <section className="space-y-3">
        <p className="text-[11px] font-semibold text-text-muted tracking-wide">Return &amp; risk</p>
        <PerformanceChartWorkspace
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
      </section>

      <section className="space-y-3">
        <p className="text-[11px] font-semibold text-text-muted tracking-wide">Positions</p>
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
        <p className="text-[11px] font-semibold text-text-muted tracking-wide">Diagnostics</p>
        <div className="glass-card overflow-hidden">
          <button
            type="button"
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="w-full flex items-center justify-between px-6 py-4 hover:bg-white/[0.02] transition-colors"
          >
            <h3 className="text-lg font-semibold">Advanced statistics</h3>
            {showAdvanced ? (
              <ChevronUp size={18} className="text-text-muted" />
            ) : (
              <ChevronDown size={18} className="text-text-muted" />
            )}
          </button>
          {showAdvanced && serverMetrics && <ServerMetricsStrip m={serverMetrics} />}
          {showAdvanced && <AdvancedStatsPanel snaps={snaps} benchmarks={benchmarks} />}
        </div>
      </section>
    </div>
  );
}
