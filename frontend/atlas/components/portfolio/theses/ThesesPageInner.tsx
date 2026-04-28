'use client';

import { useMemo, useCallback } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useDashboard } from '@/lib/dashboard-context';
import { SUBPAGE_MAX } from '@/components/subpage-tab-bar';
import PortfolioSectionNav from '@/components/portfolio/PortfolioSectionNav';
import ThesesTab from '@/components/portfolio/tabs/ThesesTab';
import AtlasLoader from '@/components/AtlasLoader';
import type { Doc, Position, Thesis } from '@/lib/types';
import type { MiniCalendarRunKind } from '@/components/library/MiniCalendar';
import { getDocLibraryTier } from '@/lib/library-doc-tier';
import { aggregateWeightByThesis } from '@/lib/portfolio-aggregates';

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

export default function ThesesPageInner() {
  const { data, loading, error } = useDashboard();
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const theses = useMemo(() => data?.portfolio?.strategy?.theses ?? [], [data]);
  const positionHistory = useMemo(() => data?.position_history ?? [], [data]);
  const lastUpdated = data?.portfolio?.meta?.last_updated ?? null;

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

  const thesisPositionsForHistoryDate = useMemo((): Pick<Position, 'weight_actual' | 'thesis_ids'>[] => {
    if (!effHistoryDate) return [];
    return positionHistory
      .filter((r) => r.date === effHistoryDate)
      .map((r) => ({
        weight_actual: r.weight_pct,
        thesis_ids: r.thesis_id ? [r.thesis_id] : [],
      }));
  }, [effHistoryDate, positionHistory]);

  const byThesisWeightForHistoryDate = useMemo(
    () => aggregateWeightByThesis(thesisPositionsForHistoryDate),
    [thesisPositionsForHistoryDate]
  );

  const thesisBookRowsForHistoryDate = useMemo(() => {
    const rows: { id: string; thesis: Thesis | null; weight: number }[] = [];
    for (const t of theses) {
      rows.push({ id: t.id, thesis: t, weight: byThesisWeightForHistoryDate.get(t.id) ?? 0 });
    }
    const unlinked = byThesisWeightForHistoryDate.get('_unlinked') ?? 0;
    if (unlinked > 0.005) {
      rows.push({ id: '_unlinked', thesis: null, weight: unlinked });
    }
    return rows.sort((a, b) => b.weight - a.weight);
  }, [theses, byThesisWeightForHistoryDate]);

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

  const selectAnalysisDate = useCallback(
    (iso: string) => {
      if (!historyDateSet.has(iso)) return;
      const p = new URLSearchParams(searchParams.toString());
      p.set('date', iso);
      router.replace(`${pathname}?${p.toString()}`, { scroll: false });
    },
    [historyDateSet, pathname, router, searchParams]
  );

  const clearHistoryDateParam = useCallback(() => {
    const p = new URLSearchParams(searchParams.toString());
    p.delete('date');
    router.replace(`${pathname}?${p.toString()}`, { scroll: false });
  }, [pathname, router, searchParams]);

  if (loading) return <AtlasLoader />;
  if (error || !data)
    return (
      <div className="flex items-center justify-center h-screen text-fin-red">
        {error || 'Failed to load'}
      </div>
    );

  return (
    <div className="flex min-h-full flex-col">
      <PortfolioSectionNav active="theses" />
      <div className={`${SUBPAGE_MAX} flex-1 space-y-6 py-4 md:py-5`}>
        <ThesesTab
          historyTimelineDates={historyTimelineDates}
          portfolioHistoryRunKindByDate={portfolioHistoryRunKindByDate}
          effHistoryDate={effHistoryDate}
          onSelectHistoryDate={selectAnalysisDate}
          historyLatestDate={historyLatestDate}
          onClearHistoryDate={clearHistoryDateParam}
          thesisBookRowsForHistoryDate={thesisBookRowsForHistoryDate}
          lastUpdated={lastUpdated}
          portfolioDocDates={portfolioDocDates}
          positionHistoryDates={positionHistoryDates}
          pipelineObservability={data.pipeline_observability ?? null}
        />
      </div>
    </div>
  );
}
