'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useDashboard } from '@/lib/dashboard-context';
import { SUBPAGE_MAX } from '@/components/subpage-tab-bar';
import PortfolioSectionNav from '@/components/portfolio/PortfolioSectionNav';
import type { PortfolioSectionId } from '@/components/portfolio/PortfolioSectionNav';
import { getDocLibraryTier, isPortfolioRecommendationPath } from '@/lib/library-doc-tier';
import { useLibraryDocument } from '@/lib/hooks/use-library-document';
import type { Doc } from '@/lib/types';
import type { MiniCalendarRunKind } from '@/components/library/MiniCalendar';
import { sortPmDocs } from './tabs/palette-and-format';
import {
  buildSleeveStackSeries,
  thesisStackLabel,
  categoryStackLabel,
  tickerStackLabel,
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
import AnalysisTab from './tabs/AnalysisTab';
import ActivityTab from './tabs/ActivityTab';
import AtlasLoader from '@/components/AtlasLoader';

function aggregateRunKindForPortfolioDocs(docsOnDate: Doc[]): MiniCalendarRunKind {
  let sawBaseline = false;
  let sawDelta = false;
  for (const d of docsOnDate) {
    const rt = (d.runType || '').toLowerCase();
    if (rt === 'baseline') sawBaseline = true;
    else if (rt === 'delta') sawDelta = true;
  }
  if (sawBaseline && sawDelta) return 'baseline';
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
  const [docKeyParam, setDocKeyParam] = useState(() => searchParams.get('docKey'));
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

  const activityEvents = positionEvents;

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

  const pmActiveFile = useMemo(() => {
    if (tab !== 'analysis' || !effHistoryDate || !data?.docs || !docKeyParam) return null;
    return (
      data.docs.find(
        (d) =>
          d.date === effHistoryDate && d.path === docKeyParam && getDocLibraryTier(d) === 'portfolio'
      ) ?? null
    );
  }, [tab, effHistoryDate, data?.docs, docKeyParam]);

  const { data: pmLibraryDoc, loading: pmLoading } = useLibraryDocument(pmActiveFile);

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

  const docsForPm = data?.docs;
  const pmDocsForHistory = useMemo(() => {
    if (!effHistoryDate || !docsForPm) return [];
    return sortPmDocs(
      docsForPm.filter(
        (d) =>
          d.date === effHistoryDate &&
          getDocLibraryTier(d) === 'portfolio' &&
          !isPortfolioRecommendationPath(d.path)
      )
    );
  }, [docsForPm, effHistoryDate]);

  const historyLatestDate = historyTimelineDates[0] ?? null;
  const showHistoryDateBanner = Boolean(
    dateParam && historyDateSet.has(dateParam) && defaultHistoryDate && dateParam !== defaultHistoryDate
  );

  useEffect(() => {
    if (urlTab && VALID_PORTFOLIO_TABS.includes(urlTab as PortfolioTabId)) {
      queueMicrotask(() => {
        setTab(urlTab as PortfolioTabId);
        setDateParam(searchParams.get('date'));
        setDocKeyParam(searchParams.get('docKey'));
      });
      return;
    }

    const p = new URLSearchParams(searchParams.toString());
    const dk = p.get('docKey');
    const docDate =
      dk && data?.docs
        ? data.docs
            .filter((d) => d.path === dk && getDocLibraryTier(d) === 'portfolio')
            .sort((a, b) => b.date.localeCompare(a.date))[0]?.date
        : null;
    const target = canonicalizeLegacyPortfolioSearch(currentPathname(pathname), p, {
      defaultHistoryDate,
      lastUpdated,
      docDate,
    });
    if (!target) {
      queueMicrotask(() => {
        setTab(mapPortfolioTabFromUrl(urlTab));
        setDateParam(searchParams.get('date'));
        setDocKeyParam(searchParams.get('docKey'));
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
      setDocKeyParam(nextParams.get('docKey'));
    });
  }, [urlTab, searchParams, pathname, router, data?.docs, lastUpdated, defaultHistoryDate]);

  useEffect(() => {
    const onPopState = () => {
      const p = new URLSearchParams(window.location.search);
      setTab(mapPortfolioTabFromUrl(p.get('tab')));
      setDateParam(p.get('date'));
      setDocKeyParam(p.get('docKey'));
    };
    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, []);

  function openPmDocument(doc: Doc) {
    const p = currentSearchParams(searchParams);
    const curKey = docKeyParam;
    const curDate = dateParam;
    if (curKey === doc.path && curDate === doc.date && tab === 'analysis') {
      closePmDocument();
      return;
    }
    p.set('tab', 'analysis');
    p.set('date', doc.date);
    p.set('docKey', doc.path);
    p.delete('thesis');
    replaceBrowserUrl(hrefWithQuery(currentPathname(pathname), p));
    setTab('analysis');
    setDateParam(doc.date);
    setDocKeyParam(doc.path);
  }

  function closePmDocument() {
    const p = currentSearchParams(searchParams);
    p.delete('docKey');
    replaceBrowserUrl(hrefWithQuery(currentPathname(pathname), p));
    setDocKeyParam(null);
  }

  function selectAnalysisDate(iso: string) {
    if (!historyDateSet.has(iso)) return;
    const p = currentSearchParams(searchParams);
    p.set('tab', 'analysis');
    p.set('date', iso);
    p.delete('docKey');
    replaceBrowserUrl(hrefWithQuery(currentPathname(pathname), p));
    setTab('analysis');
    setDateParam(iso);
    setDocKeyParam(null);
  }

  /** Sets `date` without switching away from the current tab (e.g. sleeve chart on Allocations). */
  function selectPortfolioHistoryDate(iso: string) {
    if (!historyDateSet.has(iso)) return;
    const p = currentSearchParams(searchParams);
    p.set('date', iso);
    replaceBrowserUrl(hrefWithQuery(currentPathname(pathname), p));
    setDateParam(iso);
  }

  function clearHistoryDateParam() {
    const p = currentSearchParams(searchParams);
    p.delete('date');
    p.delete('docKey');
    p.set('tab', tab);
    replaceBrowserUrl(hrefWithQuery(currentPathname(pathname), p));
    setDateParam(null);
    setDocKeyParam(null);
  }

  const sectionActive: PortfolioSectionId =
    tab === 'allocations'
      ? 'allocations'
      : tab === 'activity'
        ? 'activity'
        : tab === 'performance'
          ? 'performance'
          : 'analysis';

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
        {tab === 'allocations' && (
          <AllocationsTab
            lastUpdated={lastUpdated}
            positions={positions}
            positionHistory={positionHistory}
            positionEvents={positionEvents}
            thesisById={thesisById}
            effHistoryDate={effHistoryDate}
            onSelectHistoryDate={selectPortfolioHistoryDate}
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

        {tab === 'performance' && <PerformanceTab />}

        {tab === 'analysis' && (
          <AnalysisTab
            historyTimelineDates={historyTimelineDates}
            portfolioHistoryRunKindByDate={portfolioHistoryRunKindByDate}
            effHistoryDate={effHistoryDate}
            onSelectHistoryDate={selectAnalysisDate}
            historyLatestDate={historyLatestDate}
            onClearHistoryDate={clearHistoryDateParam}
            portfolioDocDates={portfolioDocDates}
            positionHistoryDates={positionHistoryDates}
            pmDocsForHistory={pmDocsForHistory}
            pmActiveFile={pmActiveFile}
            pmLibraryDoc={pmLibraryDoc}
            pmLoading={pmLoading}
            onOpenPmDocument={openPmDocument}
            onClosePmDocument={closePmDocument}
          />
        )}

        {tab === 'activity' && (
          <ActivityTab activityEvents={activityEvents} thesisById={thesisById} lastRunDate={lastUpdated} />
        )}
      </div>
    </div>
  );
}
