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
import AllocationsTab from './tabs/AllocationsTab';
import PerformanceTab from './tabs/PerformanceTab';
import AnalysisTab from './tabs/AnalysisTab';
import ActivityTab from './tabs/ActivityTab';
import AtlasLoader from '@/components/AtlasLoader';

type TabId = 'allocations' | 'performance' | 'analysis' | 'activity';

const VALID_TABS: TabId[] = ['allocations', 'performance', 'analysis', 'activity'];

const LEGACY_TAB_ALIASES = new Set([
  'summary',
  'history',
  'pm_process',
  'thesis',
  'positions',
  'theses',
  'pm_analysis',
]);

function mapPortfolioTabFromUrl(raw: string | null): TabId {
  if (!raw || raw === 'summary') return 'allocations';
  if (raw === 'history' || raw === 'pm_process') return 'analysis';
  if (raw === 'thesis' || raw === 'theses' || raw === 'pm_analysis' || raw === 'positions') {
    return 'allocations';
  }
  if (VALID_TABS.includes(raw as TabId)) return raw as TabId;
  return 'allocations';
}

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
  const urlDocKey = searchParams.get('docKey');
  const tab = useMemo(() => mapPortfolioTabFromUrl(urlTab), [urlTab]);
  const [sleeveStackMode, setSleeveStackMode] = useState<SleeveStackMode>('ticker');
  const { data: pmLibraryDoc, loading: pmLoading } = useLibraryDocument(pmActiveFile);

  const positions = useMemo(() => data?.positions ?? [], [data]);
  const metrics = data?.calculated;
  const theses = useMemo(() => data?.portfolio?.strategy?.theses ?? [], [data]);
  const positionHistory = useMemo(() => data?.position_history ?? [], [data]);
  const positionEvents = useMemo(() => data?.position_events ?? [], [data]);
  const lastUpdated = data?.portfolio?.meta?.last_updated ?? null;

  const thesisById = useMemo(() => new Map(theses.map((t) => [t.id, t])), [theses]);

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

  const activityEvents = useMemo(() => positionEvents, [positionEvents]);

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

  const dateParam = searchParams.get('date');

  const effHistoryDate = useMemo(() => {
    if (dateParam && historyDateSet.has(dateParam)) return dateParam;
    return defaultHistoryDate;
  }, [dateParam, historyDateSet, defaultHistoryDate]);

  const pmActiveFile = useMemo(() => {
    if (tab !== 'analysis' || !effHistoryDate || !data?.docs || !urlDocKey) return null;
    return (
      data.docs.find(
        (d) =>
          d.date === effHistoryDate && d.path === urlDocKey && getDocLibraryTier(d) === 'portfolio'
      ) ?? null
    );
  }, [tab, effHistoryDate, data?.docs, urlDocKey]);

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
    const raw = urlTab;
    if (!raw || VALID_TABS.includes(raw as TabId) || !LEGACY_TAB_ALIASES.has(raw)) return;

    const p = new URLSearchParams(searchParams.toString());
    if (raw === 'summary') {
      p.delete('tab');
      p.delete('docKey');
      p.delete('date');
      p.delete('thesis');
    } else if (raw === 'positions') {
      p.delete('tab');
      p.delete('docKey');
      p.delete('date');
      p.delete('thesis');
    } else if (raw === 'history') {
      p.set('tab', 'analysis');
      if (!p.get('date') && defaultHistoryDate) p.set('date', defaultHistoryDate);
    } else if (raw === 'pm_process') {
      p.set('tab', 'analysis');
      if (!p.get('date') && data?.docs && lastUpdated) {
        const dk = p.get('docKey');
        if (dk) {
          const matches = data.docs
            .filter((d) => d.path === dk && getDocLibraryTier(d) === 'portfolio')
            .sort((a, b) => b.date.localeCompare(a.date));
          p.set('date', matches[0]?.date ?? lastUpdated);
        } else {
          p.set('date', lastUpdated);
        }
      }
    } else if (raw === 'thesis') {
      const thesis = p.get('thesis');
      p.delete('tab');
      p.delete('date');
      p.delete('docKey');
      p.delete('thesis');
      if (thesis) {
        router.replace(`/portfolio/theses/${encodeURIComponent(thesis)}`);
        return;
      }
      router.replace('/portfolio/theses');
      return;
    } else if (raw === 'theses' || raw === 'pm_analysis') {
      p.delete('tab');
      p.delete('docKey');
      p.delete('date');
      p.delete('thesis');
      const q = p.toString();
      router.replace(q ? `/portfolio/theses?${q}` : '/portfolio/theses');
      return;
    }
    const target = p.toString();
    router.replace(target ? `${pathname}?${target}` : pathname, { scroll: false });
  }, [urlTab, searchParams, pathname, router, data?.docs, lastUpdated, defaultHistoryDate]);

  function openPmDocument(doc: Doc) {
    const p = new URLSearchParams(searchParams.toString());
    const curKey = p.get('docKey');
    const curDate = p.get('date');
    if (curKey === doc.path && curDate === doc.date && tab === 'analysis') {
      closePmDocument();
      return;
    }
    p.set('tab', 'analysis');
    p.set('date', doc.date);
    p.set('docKey', doc.path);
    p.delete('thesis');
    router.replace(`${pathname}?${p.toString()}`, { scroll: false });
  }

  function closePmDocument() {
    const p = new URLSearchParams(searchParams.toString());
    p.delete('docKey');
    router.replace(`${pathname}?${p.toString()}`, { scroll: false });
  }

  function selectAnalysisDate(iso: string) {
    if (!historyDateSet.has(iso)) return;
    const p = new URLSearchParams(searchParams.toString());
    p.set('tab', 'analysis');
    p.set('date', iso);
    p.delete('docKey');
    router.replace(`${pathname}?${p.toString()}`, { scroll: false });
  }

  /** Sets `date` without switching away from the current tab (e.g. sleeve chart on Allocations). */
  function selectPortfolioHistoryDate(iso: string) {
    if (!historyDateSet.has(iso)) return;
    const p = new URLSearchParams(searchParams.toString());
    p.set('date', iso);
    router.replace(`${pathname}?${p.toString()}`, { scroll: false });
  }

  function clearHistoryDateParam() {
    const p = new URLSearchParams(searchParams.toString());
    p.delete('date');
    p.delete('docKey');
    p.set('tab', tab);
    router.replace(`${pathname}?${p.toString()}`, { scroll: false });
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
