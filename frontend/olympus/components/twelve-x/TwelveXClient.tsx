'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { CalendarClock, CalendarDays, Layers, LineChart as LineChartIcon } from 'lucide-react';

import { SubpageStickyTabBar, SUBPAGE_MAX, subpageTabButtonClass } from '@/components/subpage-tab-bar';
import AtlasLoader from '@/components/AtlasLoader';
import {
  getConsensusTimeSeries,
  getEventOpinions,
  getIntelligence,
  getLatestConsensus,
  getLatestDigest,
  getTopConfluence,
  getUpcomingEvents,
} from '@/lib/twelve-x/fetch';
import { isTwelveXConfigured } from '@/lib/twelve-x/supabase';
import type {
  FxConfluenceSnapshotRow,
  FxConsensusSnapshotRow,
  FxEconomicCalendarRow,
  FxEventSnapshotRow,
} from '@/lib/twelve-x/types';
import TodayTab from './TodayTab';
import ConsensusTab from './ConsensusTab';
import IntelligenceTab from './IntelligenceTab';
import EventsTab from './EventsTab';

type TwelveXTab = 'today' | 'consensus' | 'intelligence' | 'events';

type DigestData = Awaited<ReturnType<typeof getLatestDigest>>;

interface TwelveXData {
  digest: DigestData;
  confluence: FxConfluenceSnapshotRow[];
  consensusSeries: FxConsensusSnapshotRow[];
  latestConsensus: FxConsensusSnapshotRow[];
  intelligence: FxConfluenceSnapshotRow[];
  upcomingEvents: FxEconomicCalendarRow[];
  eventOpinions: FxEventSnapshotRow[];
}

function resolveTab(urlTab: string | null): TwelveXTab {
  if (urlTab === 'consensus') return 'consensus';
  if (urlTab === 'intelligence') return 'intelligence';
  if (urlTab === 'events') return 'events';
  return 'today';
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

  const tab: TwelveXTab = resolveTab(urlTab);

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
        const [digest, consensusSeries, latestConsensus, intelligence, upcomingEvents] =
          await Promise.all([
            getLatestDigest(),
            getConsensusTimeSeries(),
            getLatestConsensus(),
            // Intelligence: full ranked confluence set for the latest run_date.
            getIntelligence(),
            // Events: the upcoming 14-day macro calendar window.
            getUpcomingEvents(),
          ]);
        // Confluence keys off the digest run_date so Today shows ideas for the
        // same session as the greeting.
        const confluence = digest?.run_date ? await getTopConfluence(digest.run_date) : [];
        // Event opinions key off the intelligence run_date (latest confluence run)
        // so the catalysts tab shows desk views for the freshest session.
        const opinionsDate = intelligence[0]?.run_date ?? digest?.run_date ?? null;
        const eventOpinions = opinionsDate ? await getEventOpinions(opinionsDate) : [];
        if (cancelled) return;
        setData({
          digest,
          confluence,
          consensusSeries,
          latestConsensus,
          intelligence,
          upcomingEvents,
          eventOpinions,
        });
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

  const intelligenceDate = useMemo(
    () => data?.intelligence[0]?.run_date ?? null,
    [data?.intelligence]
  );

  const eventOpinionsDate = useMemo(
    () => data?.eventOpinions[0]?.run_date ?? intelligenceDate,
    [data?.eventOpinions, intelligenceDate]
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
        <button
          type="button"
          onClick={() => setTab('intelligence')}
          className={subpageTabButtonClass(tab === 'intelligence')}
        >
          <Layers size={16} aria-hidden />
          Intelligence
        </button>
        <button
          type="button"
          onClick={() => setTab('events')}
          className={subpageTabButtonClass(tab === 'events')}
        >
          <CalendarDays size={16} aria-hidden />
          Events
        </button>
      </SubpageStickyTabBar>

      <div className={`${SUBPAGE_MAX} flex-1 space-y-4 py-4 md:py-5`}>
        {tab === 'consensus' ? (
          <ConsensusTab
            series={data?.consensusSeries ?? []}
            latest={data?.latestConsensus ?? []}
            latestDate={latestConsensusDate}
          />
        ) : tab === 'intelligence' ? (
          <IntelligenceTab confluence={data?.intelligence ?? []} runDate={intelligenceDate} />
        ) : tab === 'events' ? (
          <EventsTab
            events={data?.upcomingEvents ?? []}
            opinions={data?.eventOpinions ?? []}
            runDate={eventOpinionsDate}
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
