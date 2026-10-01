'use client';

import { Suspense, useMemo } from 'react';
import { useSearchParams } from 'next/navigation';
import HouseIdentityChrome from '@/components/house/HouseIdentityChrome';
import { BookPanel, CorpusPanel, ProfilePanel } from '@/components/house/HousePanels';
import PageSkeleton from '@/components/page-skeleton';
import { SUBPAGE_MAX } from '@/components/layout-constants';
import { usePageHeader } from '@/components/shell/page-header';
import { useDashboard } from '@/lib/dashboard-context';
import { mapHouseTabFromUrl } from '@/lib/house-identity';
import { buildBookView, buildCorpusView, buildProfileView, houseFreshness } from '@/lib/house-view';

const TITLES = { corpus: 'House corpus', book: 'House book', profile: 'House profile' } as const;

function HousePageInner() {
  const searchParams = useSearchParams();
  const tab = mapHouseTabFromUrl(searchParams.get('tab'));
  const { data, dbStatus, error } = useDashboard();
  usePageHeader({ title: TITLES[tab] });

  const corpus = useMemo(
    () => buildCorpusView(data?.docs, data?.delta_request_meta_by_date),
    [data?.docs, data?.delta_request_meta_by_date]
  );
  const book = useMemo(
    () => buildBookView(data?.positions, data?.portfolio?.snapshots, data?.calculated?.cash_pct),
    [data?.positions, data?.portfolio?.snapshots, data?.calculated?.cash_pct]
  );
  const profile = useMemo(
    () => buildProfileView(data?.positions, data?.portfolio_management?.constraints),
    [data?.positions, data?.portfolio_management?.constraints]
  );

  const meta = data?.portfolio?.meta;
  const freshness = houseFreshness(meta?.last_run_at);
  // Non-null (possibly empty) cause only when the data source is down; /house is DB-exempt.
  const unavailable = dbStatus !== 'ok' ? `Data source ${dbStatus}.` : error ? String(error) : null;

  return (
    <div className="flex min-h-full flex-col">
      <HouseIdentityChrome
        active={tab}
        freshness={freshness}
        runType={meta?.latest_snapshot_run_type ?? null}
      />
      <div className={`${SUBPAGE_MAX} flex-1 space-y-6 py-4 md:py-5`}>
        {tab === 'corpus' ? <CorpusPanel view={corpus} unavailable={unavailable} /> : null}
        {tab === 'book' ? <BookPanel view={book} unavailable={unavailable} /> : null}
        {tab === 'profile' ? <ProfilePanel view={profile} /> : null}
      </div>
    </div>
  );
}

export default function HousePage() {
  return (
    <Suspense fallback={<PageSkeleton />}>
      <HousePageInner />
    </Suspense>
  );
}
