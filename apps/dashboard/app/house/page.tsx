'use client';

import { Suspense, useMemo } from 'react';
import { useSearchParams } from 'next/navigation';
import HouseIdentityChrome from '@/components/house/HouseIdentityChrome';
import { BookPanel, CorpusPanel, ProfilePanel } from '@/components/house/HousePanels';
import PageSkeleton from '@/components/page-skeleton';
import { SUBPAGE_MAX } from '@/components/layout-constants';
import { useDashboard } from '@/lib/dashboard-context';
import { mapHouseTabFromUrl } from '@/lib/house-identity';

function HousePageInner() {
  const searchParams = useSearchParams();
  const tab = mapHouseTabFromUrl(searchParams.get('tab'));
  const { data } = useDashboard();

  const sampleKeys = useMemo(() => {
    const docs = data?.docs ?? [];
    return docs
      .map((d) => d.path || d.id || '')
      .filter(Boolean)
      .slice(0, 40);
  }, [data?.docs]);

  return (
    <div className="flex min-h-full flex-col">
      <HouseIdentityChrome active={tab} />
      <div className={`${SUBPAGE_MAX} flex-1 space-y-6 py-4 md:py-5`}>
        {tab === 'corpus' ? <CorpusPanel sampleKeys={sampleKeys} /> : null}
        {tab === 'book' ? <BookPanel /> : null}
        {tab === 'profile' ? <ProfilePanel /> : null}
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
