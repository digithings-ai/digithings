'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useDashboard } from '@/lib/dashboard-context';
import { SUBPAGE_MAX } from '@/components/subpage-tab-bar';
import PortfolioSectionNav from '@/components/portfolio/PortfolioSectionNav';
import type { PortfolioSectionId } from '@/components/portfolio/PortfolioSectionNav';
import { getDocLibraryTier } from '@/lib/library-doc-tier';
import type { Doc, Position, Thesis } from '@/lib/types';
import type { MiniCalendarRunKind } from '@/components/library/MiniCalendar';
import {
  buildSleeveStackSeries,
  thesisStackLabel,
  categoryStackLabel,
  tickerStackLabel,
  aggregateWeightByThesis,
  type SleeveStackMode,
} from '@/lib/portfolio-aggregates';
import {
  canonicalizeLegacyPortfolioSearch,
  currentPathname,
  currentSearchParams,
  hrefWithQuery,
  mapPortfolioTabFromUrl,
  replaceBrowserUrl,
  searchParamsFromHref,
  VALID_PORTFOLIO_TABS,
  type PortfolioTabId,
} from '@/lib/portfolio-url-state';
import { normalizeThesisId } from '@/lib/thesis-id';
import AllocationsTab from './tabs/AllocationsTab';
import PerformanceTab from './tabs/PerformanceTab';
import ThesesTab from './tabs/ThesesTab';
import DecisionQuality from './DecisionQuality';
import AtlasLoader from '@/components/AtlasLoader';

function aggregateRunKindForPortfolioDocs(docsOnDate: Doc[]): MiniCalendarRunKind {
  let sawBaseline = false;
  let sawDelta = false;
  for (const d of docsOnDate) {
    const rt = (d.runType || '').toLowerCase();
    if (rt === 'baseline') sawBaseline = true;
    else if (rt === 'delta') sawDelta = true;
  }
  if (sawBaseline) return 'baseline';
  if (sawDelta) return 'delta';
  return 'unknown';
}

export default function PortfolioShellInner() {
  const { data, loading, error } = useDashboard();
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const urlTab = searchParams.get('tab');
  const [tab, setTab] = useState<PortfolioTabId>(() => mapPortfolioTabFromUrl(urlTab));
  const [dateParam, setDateParam] = useState(() => searchParams.get('date'));
  const [sleeveStackMode, setSleeveStackMode] = useState<SleeveStackMode>('ticker');

  const positions = useMemo(() => data?.positions ?? [], [data]);
  const metrics = data?.calculated;
  const theses = useMemo(() => data?.portfolio?.strategy?.theses ?? [], [data]);
  const positionHistory = useMemo(() => data?.position_history ?? [], [data]);
  const positionEvents = useMemo(() => data?.position_events ?? [], [data]);
  const lastUpdated = data?.portfolio?.meta?.last_updated ?? null;

  const thesisById = useMemo(
    () => new Map(theses.map((t) => [normalizeThesisId(t.id), t])),
    [theses]
  );

  const { data: sleeveData, keys: sleeveKeys } = useMemo(
    () => buildSleeveStackSeries(positionHistory, sleeveStackMode),
    [positionHistory, sleeveStackMode]
  );

  const formatSleeveKey = useCallback(
    (k: string) => {
      if (sleeveStackMode === 'thesis') return thesisStackLabel(k, theses);
      if (sleeveStackMode === 'ticker') return tickerStackLabel(k);
      return categoryStackLabel(k);
    },
    [sleeveStackMode, theses]
  );

  const portfolioDocDates = useMemo(() => {
    const s = new Set<string>();
    for (const d of data?.docs ?? []) {
      if (d.date && getDocLibraryTier(d) === 'portfolio') s.add(d.date);
    }
    return s;
  }, [data?.docs]);

  const positionHistoryDates = useMemo(() => {
    const s = new Set<string>();
    for (const r of positionHistory) {
      if (r.date) s.add(r.date);
    }
    return s;
  }, [positionHistory]);

  const historyTimelineDates = useMemo(() => {
    const s = new Set<string>([...portfolioDocDates, ...positionHistoryDates]);
    return [...s].sort().reverse();
  }, [portfolioDocDates, positionHistoryDates]);

  const historyDateSet = useMemo(() => new Set(historyTimelineDates), [historyTimelineDates]);

  const defaultHistoryDate = useMemo(() => {
    if (lastUpdated && historyDateSet.has(lastUpdated)) return lastUpdated;
    return historyTimelineDates[0] ?? null;
  }, [lastUpdated, historyDateSet, historyTimelineDates]);

  const effHistoryDate = useMemo(() => {
    if (dateParam && historyDateSet.has(dateParam)) return dateParam;
    return defaultHistoryDate;
  }, [dateParam, historyDateSet, defaultHistoryDate]);

  const portfolioHistoryRunKindByDate = useMemo(() => {
    const m = new Map<string, MiniCalendarRunKind>();
    const docs = data?.docs ?? [];
    const snapshotRunTypeByDate = data?.snapshot_run_type_by_date ?? {};
    for (const date of historyTimelineDates) {
      const onDay = docs.filter((d) => d.date === date && getDocLibraryTier(d) === 'portfolio');
      let kind = aggregateRunKindForPortfolioDocs(onDay);
      if (kind === 'unknown') {
        const snap = snapshotRunTypeByDate[date];
        if (snap === 'baseline' || snap === 'delta') kind = snap;
      }
      m.set(date, kind);
    }
    return m;
  }, [data?.docs, data?.snapshot_run_type_by_date, historyTimelineDates]);

  const historyLatestDate = historyTimelineDates[0] ?? null;
  const showHistoryDateBanner = Boolean(
    dateParam && historyDateSet.has(dateParam) && defaultHistoryDate && dateParam !== defaultHistoryDate
  );

  // Per-thesis book weights for the selected history date (moved here from the
  // old standalone theses route so Theses can live as a Portfolio tab).
  const thesisBookRowsForHistoryDate = useMemo(() => {
    const thesisPositions: Pick<Position, 'weight_actual' | 'thesis_ids'>[] = effHistoryDate
      ? positionHistory
          .filter((r) => r.date === effHistoryDate)
          .map((r) => ({ weight_actual: r.weight_pct, thesis_ids: r.thesis_id ? [r.thesis_id] : [] }))
      : [];
    const byThesis = aggregateWeightByThesis(thesisPositions);
    const rows: { id: string; thesis: Thesis | null; weight: number }[] = [];
    for (const t of theses) {
      rows.push({ id: t.id, thesis: t, weight: byThesis.get(normalizeThesisId(t.id)) ?? 0 });
    }
    const unlinked = byThesis.get('_unlinked') ?? 0;
    if (unlinked > 0.005) rows.push({ id: '_unlinked', thesis: null, weight: unlinked });
    return rows.sort((a, b) => b.weight - a.weight);
  }, [theses, positionHistory, effHistoryDate]);

  useEffect(() => {
    if (urlTab && VALID_PORTFOLIO_TABS.includes(urlTab as PortfolioTabId)) {
      queueMicrotask(() => {
        setTab(urlTab as PortfolioTabId);
        setDateParam(searchParams.get('date'));
      });
      return;
    }

    const p = new URLSearchParams(searchParams.toString());
    const target = canonicalizeLegacyPortfolioSearch(currentPathname(pathname), p, {
      defaultHistoryDate,
      lastUpdated,
    });
    if (!target) {
      queueMicrotask(() => {
        setTab(mapPortfolioTabFromUrl(urlTab));
        setDateParam(searchParams.get('date'));
      });
      return;
    }
    if (target.kind === 'path') {
      router.replace(target.href);
      return;
    }
    replaceBrowserUrl(target.href);
    const nextParams = searchParamsFromHref(target.href);
    queueMicrotask(() => {
      setTab(mapPortfolioTabFromUrl(nextParams.get('tab')));
      setDateParam(nextParams.get('date'));
    });
  }, [urlTab, searchParams, pathname, router, lastUpdated, defaultHistoryDate]);

  useEffect(() => {
    const onPopState = () => {
      const p = new URLSearchParams(window.location.search);
      setTab(mapPortfolioTabFromUrl(p.get('tab')));
      setDateParam(p.get('date'));
    };
    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, []);

  /** Sets `date` without switching tabs (sleeve chart on Holdings, calendar on Theses). */
  const selectHistoryDate = useCallback(
    (iso: string) => {
      if (!historyDateSet.has(iso)) return;
      const p = currentSearchParams(searchParams);
      p.set('date', iso);
      replaceBrowserUrl(hrefWithQuery(currentPathname(pathname), p));
      setDateParam(iso);
    },
    [historyDateSet, pathname, searchParams]
  );

  const clearHistoryDateParam = useCallback(() => {
    const p = currentSearchParams(searchParams);
    p.delete('date');
    p.set('tab', tab);
    replaceBrowserUrl(hrefWithQuery(currentPathname(pathname), p));
    setDateParam(null);
  }, [pathname, searchParams, tab]);

  const sectionActive: PortfolioSectionId = tab;

  if (loading) return <AtlasLoader />;
  if (error || !data || !metrics)
    return (
      <div className="flex items-center justify-center h-screen text-fin-red">
        {error || 'Failed to load'}
      </div>
    );

  return (
    <div className="flex min-h-full flex-col">
      <PortfolioSectionNav active={sectionActive} />

      <div className={`${SUBPAGE_MAX} flex-1 space-y-6 py-4 md:py-5`}>
        {tab === 'holdings' && (
          <AllocationsTab
            lastUpdated={lastUpdated}
            positions={positions}
            positionHistory={positionHistory}
            positionEvents={positionEvents}
            thesisById={thesisById}
            effHistoryDate={effHistoryDate}
            onSelectHistoryDate={selectHistoryDate}
            onClearHistoryDate={clearHistoryDateParam}
            showHistoryDateBanner={showHistoryDateBanner}
            dateParam={dateParam}
            historyMode={sleeveStackMode}
            setHistoryMode={setSleeveStackMode}
            sleeveData={sleeveData}
            sleeveKeys={sleeveKeys}
            formatSleeveKey={formatSleeveKey}
          />
        )}

        {tab === 'theses' && (
          <ThesesTab
            historyTimelineDates={historyTimelineDates}
            portfolioHistoryRunKindByDate={portfolioHistoryRunKindByDate}
            effHistoryDate={effHistoryDate}
            onSelectHistoryDate={selectHistoryDate}
            historyLatestDate={historyLatestDate}
            onClearHistoryDate={clearHistoryDateParam}
            thesisBookRowsForHistoryDate={thesisBookRowsForHistoryDate}
            lastUpdated={lastUpdated}
            portfolioDocDates={portfolioDocDates}
            positionHistoryDates={positionHistoryDates}
            pipelineObservability={data.pipeline_observability ?? null}
          />
        )}

        {tab === 'performance' && (
          <div className="space-y-10">
            <PerformanceTab />
            <DecisionQuality />
          </div>
        )}
      </div>
    </div>
  );
}
