'use client';

import { useMemo } from 'react';
import { useSearchParams } from 'next/navigation';
import { SUBPAGE_MAX } from '@/components/layout-constants';
import CorpusSectionNav, { type CorpusSectionId } from '@/components/corpus/CorpusSectionNav';
import { CorpusChromeBody } from '@/components/corpus/CorpusChromePanels';

function mapCorpusTab(raw: string | null): CorpusSectionId {
  if (raw === 'book' || raw === 'profile') return raw;
  return 'corpus';
}

export default function CorpusShellInner() {
  const searchParams = useSearchParams();
  const tab = useMemo(() => mapCorpusTab(searchParams.get('tab')), [searchParams]);

  return (
    <div className="flex min-h-full flex-col">
      <CorpusSectionNav active={tab} />
      <div className={`${SUBPAGE_MAX} flex-1 space-y-6 py-4 md:py-5`}>
        <CorpusChromeBody tab={tab} />
      </div>
    </div>
  );
}
