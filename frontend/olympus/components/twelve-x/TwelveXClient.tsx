'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
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
  computeConsensusDeltaSet,
  getConsensusTimeSeries,
  getEventOpinions,
  getIntelligence,
  getLatestConsensus,
  getLatestDigest,
  getLedger,
  getLedgerRunDates,
  getMatrix,
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
import { TwelveXProvider, type TwelveXContextValue, type CrossLink, type TwelveXTab } from './context';
import { useWatchlist } from './useWatchlist';

type DigestData = Awaited<ReturnType<typeof getLatestDigest>>;

/** The workspace tab bar, in display order: id, icon, and label. */
const TABS: ReadonlyArray<{ id: TwelveXTab; Icon: typeof CalendarClock; label: string }> = [
  { id: 'today', Icon: CalendarClock, label: 'Today' },
  { id: 'consensus', Icon: LineChartIcon, label: 'Consensus' },
  { id: 'intelligence', Icon: Layers, label: 'Intelligence' },
  { id: 'events', Icon: CalendarDays, label: 'Events' },
  { id: 'matrix', Icon: Grid3x3, label: 'Matrix' },
  { id: 'ledger', Icon: ScrollText, label: 'Ledger' },
];

/** A brief drill-down target: the source_file key plus the run that owns it. */
export type BriefTarget = { sourceFile: string; runDate: string | null };

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

/** Read a query param from the live URL (client only) — used once to seed state. */
function readParam(key: string): string | null {
  if (typeof window === 'undefined') return null;
  return new URLSearchParams(window.location.search).get(key);
}

/**
 * Sync in-page state (tab / open brief / ledger currency) to the URL with
 * history.replaceState — NOT the Next router. Under this suite's static export
 * (output:'export' + trailingSlash) router.replace query-nav is unreliable and
 * was the cause of tabs not switching / blank pages, so all control flow is
 * local React state and the URL is mirrored only for deep-link/shareability.
 */
function syncUrl(tab: TwelveXTab, brief: BriefTarget | null, ledgerCcy: string | null): void {
  if (typeof window === 'undefined') return;
  const p = new URLSearchParams();
  if (tab !== 'today') p.set('tab', tab);
  if (brief?.sourceFile) {
    p.set('brief', brief.sourceFile);
    if (brief.runDate) p.set('briefDate', brief.runDate);
  }
  if (ledgerCcy) p.set('ledgerCcy', ledgerCcy);
  const qs = p.toString();
  const url = qs ? `${window.location.pathname}?${qs}` : window.location.pathname;
  window.history.replaceState(window.history.state, '', url);
}

export default function TwelveXClient() {
  // Resolve configuration once, synchronously, so the effect never has to call
  // setState in its body (which triggers cascading renders).
  const [configured] = useState(() => isTwelveXConfigured());
  const [data, setData] = useState<TwelveXData | null>(null);
  const [loading, setLoading] = useState(configured);
  const [error, setError] = useState<string | null>(configured ? null : 'unconfigured');

  // In-page navigation state — local, seeded once from the URL for deep links.
  const [tab, setTabState] = useState<TwelveXTab>(() => resolveTab(readParam('tab')));
  const [brief, setBrief] = useState<BriefTarget | null>(() => {
    const sf = readParam('brief');
    return sf ? { sourceFile: sf, runDate: readParam('briefDate') } : null;
  });
  const [ledgerCcy, setLedgerCcy] = useState<string | null>(() => readParam('ledgerCcy'));

  // Ledger (P4) loads lazily by selected run_date so the audit table can be
  // re-pointed without refetching the whole workspace.
  const [ledgerRun, setLedgerRun] = useState<string | null>(null);
  const [ledgerRows, setLedgerRows] = useState<FxLedgerRow[]>([]);
  const [ledgerError, setLedgerError] = useState<string | null>(null);

  // Cross-link focus targets handed to the destination tabs.
  const [consensusFocusCcy, setConsensusFocusCcy] = useState<string | null>(null);
  const [eventFocus, setEventFocus] = useState<{ externalId?: string | null; name: string | null } | null>(
    null
  );

  const setTab = useCallback(
    (next: TwelveXTab) => {
      setTabState(next);
      syncUrl(next, brief, ledgerCcy);
    },
    [brief, ledgerCcy]
  );

  const openBrief = useCallback(
    (sourceFile: string, runDate: string | null) => {
      const next = { sourceFile, runDate };
      setBrief(next);
      syncUrl(tab, next, ledgerCcy);
    },
    [tab, ledgerCcy]
  );

  const closeBrief = useCallback(() => {
    setBrief(null);
    syncUrl(tab, null, ledgerCcy);
  }, [tab, ledgerCcy]);

  // "Why this weight?" from a consensus cell → jump to the ledger tab, pre-filtered
  // to that currency.
  const drillToLedger = useCallback(
    (currency: string) => {
      setTabState('ledger');
      setLedgerCcy(currency);
      syncUrl('ledger', brief, currency);
    },
    [brief]
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
        // Today's "top trade ideas" are the top of the SAME ranked set the
        // Intelligence tab shows (the latest confluence run) — not the digest's
        // run_date, which can lag the latest confluence run (e.g. a digest exists
        // for a day with no confluence) and leave Today empty while Intelligence
        // has ideas. Slicing `intelligence` keeps the two surfaces consistent.
        const confluence = intelligence.slice(0, 6);
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

  // Run-over-run consensus deltas (pure, derived from the fetched series).
  const consensusDeltas = useMemo(
    () => computeConsensusDeltaSet(data?.consensusSeries ?? []),
    [data?.consensusSeries]
  );

  // The single canonical "as-of" run the workspace reports, preferring the
  // digest's run, then intelligence, then the latest consensus run.
  const canonicalRunDate = useMemo(
    () => data?.digest?.run_date ?? intelligenceDate ?? latestConsensusDate,
    [data?.digest?.run_date, intelligenceDate, latestConsensusDate]
  );

  // Load the ledger audit rows for the selected run (P4). Re-runs whenever the
  // picker changes; independent of the main workspace load.
  useEffect(() => {
    if (!configured || !ledgerRun) return;
    let cancelled = false;
    (async () => {
      try {
        const rows = await getLedger(ledgerRun);
        if (!cancelled) {
          setLedgerRows(rows);
          setLedgerError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setLedgerRows([]);
          setLedgerError(err instanceof Error ? err.message : 'Failed to load the relevance ledger');
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [configured, ledgerRun]);

  const watchlist = useWatchlist();

  // The shared cross-surface navigator handed to every tab via context.
  const crossLink = useCallback(
    (l: CrossLink) => {
      switch (l.kind) {
        case 'currency':
          setTabState('consensus');
          setConsensusFocusCcy(l.currency);
          syncUrl('consensus', brief, ledgerCcy);
          break;
        case 'ledger':
          drillToLedger(l.currency);
          break;
        case 'brief':
          openBrief(l.sourceFile, l.runDate);
          break;
        case 'event':
          setTabState('events');
          setEventFocus({ externalId: l.externalId ?? null, name: l.eventName });
          syncUrl('events', brief, ledgerCcy);
          break;
        case 'tab':
          setTab(l.tab);
          break;
      }
    },
    [brief, ledgerCcy, drillToLedger, openBrief, setTab]
  );

  const ctx = useMemo<TwelveXContextValue>(
    () => ({ runDate: canonicalRunDate, crossLink, openBrief, watchlist }),
    [canonicalRunDate, crossLink, openBrief, watchlist]
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

  const renderActiveTab = () => {
    switch (tab) {
      case 'consensus':
        return (
          <ConsensusTab
            series={data?.consensusSeries ?? []}
            latest={data?.latestConsensus ?? []}
            latestDate={latestConsensusDate}
            onDrillToLedger={drillToLedger}
            deltas={consensusDeltas}
            focusCcy={consensusFocusCcy}
          />
        );
      case 'intelligence':
        return (
          <IntelligenceTab
            confluence={data?.intelligence ?? []}
            runDate={intelligenceDate}
            events={data?.eventOpinions ?? []}
          />
        );
      case 'events':
        return (
          <EventsTab
            events={data?.upcomingEvents ?? []}
            opinions={data?.eventOpinions ?? []}
            runDate={eventOpinionsDate}
            onOpenBrief={openBrief}
            focus={eventFocus}
          />
        );
      case 'matrix':
        return <MatrixTab cells={data?.matrix ?? []} onOpenBrief={openBrief} />;
      case 'ledger':
        return (
          <LedgerTab
            rows={ledgerRows}
            runDate={ledgerRun}
            runDates={data?.ledgerRunDates ?? []}
            onSelectRun={setLedgerRun}
            ccy={ledgerCcy}
            onOpenBrief={openBrief}
            error={ledgerError}
          />
        );
      default:
        return (
          <TodayTab
            digest={data?.digest ?? null}
            confluence={data?.confluence ?? []}
            runDate={canonicalRunDate}
            movers={consensusDeltas.movers}
            deltas={consensusDeltas}
          />
        );
    }
  };

  return (
    <div className="flex min-h-full flex-col">
      <SubpageStickyTabBar aria-label="FX research workspace" topOffset="none">
        {TABS.map(({ id, Icon, label }) => (
          <button
            key={id}
            type="button"
            onClick={() => setTab(id)}
            className={subpageTabButtonClass(tab === id)}
          >
            <Icon size={16} aria-hidden />
            {label}
          </button>
        ))}
      </SubpageStickyTabBar>

      <TwelveXProvider value={ctx}>
        <div className={`${SUBPAGE_MAX} flex-1 space-y-4 py-4 md:py-5`}>{renderActiveTab()}</div>

        {/* Slide-over brief panel — local state, no router. */}
        <BriefPanel
          open={!!brief}
          sourceFile={brief?.sourceFile ?? null}
          runDate={brief?.runDate ?? null}
          onClose={closeBrief}
        />
      </TwelveXProvider>
    </div>
  );
}
