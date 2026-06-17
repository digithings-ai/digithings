'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { CalendarClock, LineChart as LineChartIcon } from 'lucide-react';

import { SubpageStickyTabBar, SUBPAGE_MAX, subpageTabButtonClass } from '@/components/subpage-tab-bar';
import AtlasLoader from '@/components/AtlasLoader';
import {
  getConsensusTimeSeries,
  getLatestConsensus,
  getLatestDigest,
  getTopConfluence,
} from '@/lib/twelve-x/fetch';
import { isTwelveXConfigured } from '@/lib/twelve-x/supabase';
import type { FxConfluenceSnapshotRow, FxConsensusSnapshotRow } from '@/lib/twelve-x/types';
import TodayTab from './TodayTab';
import ConsensusTab from './ConsensusTab';

type TwelveXTab = 'today' | 'consensus';

type DigestData = Awaited<ReturnType<typeof getLatestDigest>>;

interface TwelveXData {
  digest: DigestData;
  confluence: FxConfluenceSnapshotRow[];
  consensusSeries: FxConsensusSnapshotRow[];
  latestConsensus: FxConsensusSnapshotRow[];
}

function TwelveXInner({ urlTab }: { urlTab: string | null }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  // Resolve configuration once, synchronously, so the effect never has to call
  // setState in its body (which triggers cascading renders).
  const [configured] = useState(() => isTwelveXConfigured());
  const [data, setData] = useState<TwelveXData | null>(null);
  const [loading, setLoading] = useState(configured);
  const [error, setError] = useState<string | null>(configured ? null : 'unconfigured');

  const tab: TwelveXTab = urlTab === 'consensus' ? 'consensus' : 'today';

  const replaceQuery = useCallback(
    (mutate: (p: URLSearchParams) => void) => {
      const p = new URLSearchParams(searchParams.toString());
      mutate(p);
      const s = p.toString();
      router.replace(s ? `${pathname}?${s}` : pathname, { scroll: false });
    },
    [pathname, router, searchParams]
  );

  const setTab = useCallback(
    (next: TwelveXTab) => {
      replaceQuery((p) => p.set('tab', next));
    },
    [replaceQuery]
  );

  useEffect(() => {
    if (!configured) return;
    let cancelled = false;
    (async () => {
      try {
        const [digest, consensusSeries, latestConsensus] = await Promise.all([
          getLatestDigest(),
          getConsensusTimeSeries(),
          getLatestConsensus(),
        ]);
        // Confluence keys off the digest run_date so Today shows ideas for the
        // same session as the greeting.
        const confluence = digest?.run_date ? await getTopConfluence(digest.run_date) : [];
        if (cancelled) return;
        setData({ digest, confluence, consensusSeries, latestConsensus });
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : 'Failed to load FX research data');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [configured]);

  const latestConsensusDate = useMemo(
    () => data?.latestConsensus[0]?.run_date ?? null,
    [data?.latestConsensus]
  );

  if (loading) return <AtlasLoader />;

  if (error === 'unconfigured') {
    return (
      <div className={`${SUBPAGE_MAX} py-10`}>
        <div className="glass-card p-10 text-center text-text-muted text-sm">
          FX research is not configured. Set{' '}
          <code className="font-mono text-text-secondary">NEXT_PUBLIC_TWELVEX_SUPABASE_URL</code> and{' '}
          <code className="font-mono text-text-secondary">NEXT_PUBLIC_TWELVEX_SUPABASE_ANON_KEY</code>{' '}
          (or the shared Supabase env vars).
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className={`${SUBPAGE_MAX} py-10`}>
        <div className="glass-card p-10 text-center text-fin-red text-sm">{error}</div>
      </div>
    );
  }

  return (
    <div className="flex min-h-full flex-col">
      <SubpageStickyTabBar aria-label="FX research workspace">
        <button type="button" onClick={() => setTab('today')} className={subpageTabButtonClass(tab === 'today')}>
          <CalendarClock size={16} aria-hidden />
          Today
        </button>
        <button
          type="button"
          onClick={() => setTab('consensus')}
          className={subpageTabButtonClass(tab === 'consensus')}
        >
          <LineChartIcon size={16} aria-hidden />
          Consensus
        </button>
      </SubpageStickyTabBar>

      <div className={`${SUBPAGE_MAX} flex-1 space-y-4 py-4 md:py-5`}>
        {tab === 'consensus' ? (
          <ConsensusTab
            series={data?.consensusSeries ?? []}
            latest={data?.latestConsensus ?? []}
            latestDate={latestConsensusDate}
          />
        ) : (
          <TodayTab digest={data?.digest ?? null} confluence={data?.confluence ?? []} />
        )}
      </div>
    </div>
  );
}

export default function TwelveXClient() {
  const searchParams = useSearchParams();
  const urlTab = searchParams.get('tab');
  return <TwelveXInner urlTab={urlTab} />;
}
