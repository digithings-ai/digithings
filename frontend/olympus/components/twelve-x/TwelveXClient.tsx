'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import {
  CalendarClock,
  CalendarDays,
  Grid3x3,
  Layers,
  LineChart as LineChartIcon,
  ScrollText,
} from 'lucide-react';

import { SubpageStickyTabBar, SUBPAGE_MAX, subpageTabButtonClass } from '@/components/subpage-tab-bar';
import AtlasLoader from '@/components/AtlasLoader';
import {
  getConsensusTimeSeries,
  getEventOpinions,
  getIntelligence,
  getLatestConsensus,
  getLatestDigest,
  getLedger,
  getLedgerRunDates,
  getMatrix,
  getTopConfluence,
  getUpcomingEvents,
} from '@/lib/twelve-x/fetch';
import { isTwelveXConfigured } from '@/lib/twelve-x/supabase';
import type {
  FxConfluenceSnapshotRow,
  FxConsensusSnapshotRow,
  FxEconomicCalendarRow,
  FxEventSnapshotRow,
  FxLedgerRow,
  MatrixCell,
} from '@/lib/twelve-x/types';
import TodayTab from './TodayTab';
import ConsensusTab from './ConsensusTab';
import IntelligenceTab from './IntelligenceTab';
import EventsTab from './EventsTab';
import MatrixTab from './MatrixTab';
import LedgerTab from './LedgerTab';
import BriefPanel from './BriefPanel';

type TwelveXTab = 'today' | 'consensus' | 'intelligence' | 'events' | 'matrix' | 'ledger';

type DigestData = Awaited<ReturnType<typeof getLatestDigest>>;

interface TwelveXData {
  digest: DigestData;
  confluence: FxConfluenceSnapshotRow[];
  consensusSeries: FxConsensusSnapshotRow[];
  latestConsensus: FxConsensusSnapshotRow[];
  intelligence: FxConfluenceSnapshotRow[];
  upcomingEvents: FxEconomicCalendarRow[];
  eventOpinions: FxEventSnapshotRow[];
  matrix: MatrixCell[];
  ledgerRunDates: string[];
}

function resolveTab(urlTab: string | null): TwelveXTab {
  if (urlTab === 'consensus') return 'consensus';
  if (urlTab === 'intelligence') return 'intelligence';
  if (urlTab === 'events') return 'events';
  if (urlTab === 'matrix') return 'matrix';
  if (urlTab === 'ledger') return 'ledger';
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

  // Ledger (P4) loads lazily by selected run_date so the audit table can be
  // re-pointed without refetching the whole workspace.
  const [ledgerRun, setLedgerRun] = useState<string | null>(null);
  const [ledgerRows, setLedgerRows] = useState<FxLedgerRow[]>([]);

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

  // "Why this weight?" from a consensus cell → jump to the ledger tab, pre-filtered
  // to that currency (ledgerCcy is read by LedgerTab as its initial currency filter).
  const drillToLedger = useCallback(
    (currency: string) => {
      replaceQuery((p) => {
        p.set('tab', 'ledger');
        p.set('ledgerCcy', currency);
      });
    },
    [replaceQuery]
  );

  useEffect(() => {
    if (!configured) return;
    let cancelled = false;
    (async () => {
      try {
        const [
          digest,
          consensusSeries,
          latestConsensus,
          intelligence,
          upcomingEvents,
          matrix,
          ledgerRunDates,
        ] = await Promise.all([
          getLatestDigest(),
          getConsensusTimeSeries(),
          getLatestConsensus(),
          // Intelligence: full ranked confluence set for the latest run_date.
          getIntelligence(),
          // Events: the upcoming 14-day macro calendar window.
          getUpcomingEvents(),
          // Matrix (P3): latest desk view per (broker, currency) over a window.
          getMatrix(),
          // Ledger (P4): run picker options.
          getLedgerRunDates(),
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
          matrix,
          ledgerRunDates,
        });
        // Default the ledger to the freshest run present.
        setLedgerRun((prev) => prev ?? ledgerRunDates[0] ?? null);
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

  // Load the ledger audit rows for the selected run (P4). Re-runs whenever the
  // picker changes; independent of the main workspace load.
  useEffect(() => {
    if (!configured || !ledgerRun) return;
    let cancelled = false;
    (async () => {
      try {
        const rows = await getLedger(ledgerRun);
        if (!cancelled) setLedgerRows(rows);
      } catch {
        if (!cancelled) setLedgerRows([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [configured, ledgerRun]);

  const selectLedgerRun = useCallback((next: string) => setLedgerRun(next), []);

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
        <button
          type="button"
          onClick={() => setTab('matrix')}
          className={subpageTabButtonClass(tab === 'matrix')}
        >
          <Grid3x3 size={16} aria-hidden />
          Matrix
        </button>
        <button
          type="button"
          onClick={() => setTab('ledger')}
          className={subpageTabButtonClass(tab === 'ledger')}
        >
          <ScrollText size={16} aria-hidden />
          Ledger
        </button>
      </SubpageStickyTabBar>

      <div className={`${SUBPAGE_MAX} flex-1 space-y-4 py-4 md:py-5`}>
        {tab === 'consensus' ? (
          <ConsensusTab
            series={data?.consensusSeries ?? []}
            latest={data?.latestConsensus ?? []}
            latestDate={latestConsensusDate}
            onDrillToLedger={drillToLedger}
          />
        ) : tab === 'intelligence' ? (
          <IntelligenceTab confluence={data?.intelligence ?? []} runDate={intelligenceDate} />
        ) : tab === 'events' ? (
          <EventsTab
            events={data?.upcomingEvents ?? []}
            opinions={data?.eventOpinions ?? []}
            runDate={eventOpinionsDate}
          />
        ) : tab === 'matrix' ? (
          <MatrixTab cells={data?.matrix ?? []} />
        ) : tab === 'ledger' ? (
          <LedgerTab
            rows={ledgerRows}
            runDate={ledgerRun}
            runDates={data?.ledgerRunDates ?? []}
            onSelectRun={selectLedgerRun}
          />
        ) : (
          <TodayTab digest={data?.digest ?? null} confluence={data?.confluence ?? []} />
        )}
      </div>

      {/* Slide-over brief panel — opens on ?brief=<source_file> from any tab. */}
      <BriefPanel />
    </div>
  );
}

export default function TwelveXClient() {
  const searchParams = useSearchParams();
  const urlTab = searchParams.get('tab');
  return <TwelveXInner urlTab={urlTab} />;
}
