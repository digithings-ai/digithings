'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  CalendarClock,
  CalendarDays,
  ClipboardList,
  Grid3x3,
  LineChart as LineChartIcon,
  Workflow,
} from 'lucide-react';
import { EmptyState } from '@digithings/web';

import { SUBPAGE_MAX } from '@/components/layout-constants';
import { SubpageStickyTabBar, subpageTabButtonClass } from '@/components/subpage-tab-bar';
import PageSkeleton from '@/components/page-skeleton';
import {
  computeConsensusDeltaSet,
  getConsensusDivergence,
  getConsensusTimeSeries,
  getEventOpinions,
  getIdeaEval,
  getConsensusEval,
  getIntelligence,
  getIntelligenceWhy,
  getLatestDigest,
  getMatrix,
  getTradeIdeaArchive,
  getTradeIdeas,
  getTradeIdeaHistory,
  getTodayBriefs,
  getTodayEvents,
  getUpcomingEvents,
  getBriefs,
} from '@/lib/twelve-x/fetch';
import { selectLatestCompleteConsensus } from '@/lib/twelve-x/consensus-derive';
import { isTwelveXConfigured } from '@/lib/twelve-x/supabase';
import type {
  FxBriefRow,
  FxConfluenceSnapshotRow,
  FxConsensusDivergence,
  FxConsensusEvalRow,
  FxConsensusSnapshotRow,
  FxEconomicCalendarRow,
  FxEventSnapshotRow,
  FxIdeaEvalRow,
  FxTradeIdeaRow,
  IntelligenceWhy,
  MatrixCell,
} from '@/lib/twelve-x/types';
import TodayTab from './TodayTab';
import BriefsIndex from './BriefsIndex';
import ConsensusTab from './ConsensusTab';
import EventsTab from './EventsTab';
import HowItWorksTab from './HowItWorksTab';
import MatrixTab from './MatrixTab';
import TradesTab from './TradesTab';
import BriefPanel from './BriefPanel';
import TwelveXHeading from './TwelveXHeading';
import { TwelveXProvider, type TwelveXContextValue, type CrossLink, type TwelveXTab } from './context';
import { useWatchlist } from './useWatchlist';

type DigestData = Awaited<ReturnType<typeof getLatestDigest>>;

/** The workspace tab bar, in display order: id, icon, and label. */
export const TWELVE_X_TABS: ReadonlyArray<{ id: TwelveXTab; Icon: typeof CalendarClock; label: string }> = [
  { id: 'today', Icon: CalendarClock, label: 'Today' },
  { id: 'consensus', Icon: LineChartIcon, label: 'Consensus' },
  { id: 'trades', Icon: ClipboardList, label: 'Trades' },
  { id: 'matrix', Icon: Grid3x3, label: 'Matrix' },
  { id: 'events', Icon: CalendarDays, label: 'Events' },
  { id: 'how-it-works', Icon: Workflow, label: 'How it works' },
];

function TwelveXTabBar({
  active,
  onSelect,
  disabled = false,
}: {
  active: TwelveXTab;
  onSelect?: (tab: TwelveXTab) => void;
  disabled?: boolean;
}) {
  return (
    <SubpageStickyTabBar aria-label="FX research workspace">
      {TWELVE_X_TABS.map(({ id, Icon, label }) => (
        <button
          key={id}
          type="button"
          disabled={disabled}
          onClick={() => onSelect?.(id)}
          className={`${subpageTabButtonClass(active === id)} disabled:cursor-not-allowed disabled:opacity-50`}
        >
          <Icon size={16} aria-hidden />
          {label}
        </button>
      ))}
    </SubpageStickyTabBar>
  );
}

export function TwelveXUnavailable({ configured }: { configured: boolean }) {
  return (
    <div className="flex min-h-full flex-col">
      <div className={`${SUBPAGE_MAX} flex-1 py-12`}>
        <EmptyState
          variant="error"
          className="mx-auto max-w-md border border-hair bg-surface"
          title={configured ? 'FX research is temporarily unavailable' : 'FX research is not connected'}
          body={
            configured
              ? 'The research feed could not be reached. Try again to reconnect.'
              : 'This environment is not connected to the FX research feed.'
          }
          action={
            <button
              type="button"
              onClick={() => window.location.reload()}
              className="mt-5 inline-flex items-center rounded-none border border-hair bg-ink px-4 py-2 text-sm font-medium text-bg transition-colors hover:bg-ink/90"
            >
              Retry
            </button>
          }
        />
      </div>
    </div>
  );
}

/** A brief drill-down target: the source_file key plus the run that owns it. */
export type BriefTarget = { sourceFile: string; runDate: string | null };

interface TwelveXData {
  digest: DigestData;
  consensusSeries: FxConsensusSnapshotRow[];
  latestConsensus: FxConsensusSnapshotRow[];
  intelligence: FxConfluenceSnapshotRow[];
  intelligenceWhy: IntelligenceWhy;
  upcomingEvents: FxEconomicCalendarRow[];
  eventOpinions: FxEventSnapshotRow[];
  matrix: MatrixCell[];
  tradeIdeas: FxTradeIdeaRow[];
  tradeIdeaHistory: Pick<FxTradeIdeaRow, 'run_date' | 'pair' | 'direction' | 'as_of'>[];
  tradeIdeaArchive: FxTradeIdeaRow[];
  todayBriefs: FxBriefRow[];
  todayEvents: FxEconomicCalendarRow[];
  researchBriefs: FxBriefRow[];
  divergenceByCurrency: Record<string, FxConsensusDivergence>;
  ideaEval: FxIdeaEvalRow[];
  consensusEval: FxConsensusEvalRow[];
}

export function resolveTab(urlTab: string | null): TwelveXTab {
  if (urlTab === 'consensus') return 'consensus';
  if (urlTab === 'trades') return 'trades';
  if (urlTab === 'track-record') return 'trades'; // Legacy redirect
  if (urlTab === 'intelligence') return 'consensus'; // Legacy redirect
  if (urlTab === 'events') return 'events';
  if (urlTab === 'matrix') return 'matrix';
  if (urlTab === 'how-it-works') return 'how-it-works';
  return 'today';
}

/** Read a query param from the live URL (client only) — used once to seed state. */
function readParam(key: string): string | null {
  if (typeof window === 'undefined') return null;
  return new URLSearchParams(window.location.search).get(key);
}

/**
 * Sync in-page state (tab / open brief) to the URL with
 * history.replaceState — NOT the Next router. Under this suite's static export
 * (output:'export' + trailingSlash) router.replace query-nav is unreliable and
 * was the cause of tabs not switching / blank pages, so all control flow is
 * local React state and the URL is mirrored only for deep-link/shareability.
 */
function syncUrl(
  tab: TwelveXTab,
  brief: BriefTarget | null,
  view: 'briefs' | null = null,
): void {
  if (typeof window === 'undefined') return;
  const p = new URLSearchParams();
  if (tab !== 'today') p.set('tab', tab);
  if (brief?.sourceFile) {
    p.set('brief', brief.sourceFile);
    if (brief.runDate) p.set('briefDate', brief.runDate);
  }
  if (view) p.set('view', view);
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

  // In-page navigation state — local, adopted from the URL for deep links.
  //
  // It cannot be seeded in the initializers. This suite is a static export, so
  // the prerendered HTML always carries the default tab, and React does not
  // repair a mismatched *attribute* while hydrating — only the children. A
  // `?tab=trades` link therefore rendered the Trades panel under a strip that
  // still highlighted Today, and the next click lit a second tab, because the
  // stale className was never written. Starting where the prerender started and
  // adopting the URL on the first post-hydration commit makes it an ordinary
  // update, which React does write out.
  const [tab, setTabState] = useState<TwelveXTab>('today');
  const [brief, setBrief] = useState<BriefTarget | null>(null);
  const [view, setView] = useState<'briefs' | null>(null);

  useEffect(() => {
    /* eslint-disable react-hooks/set-state-in-effect -- the cascade is the
     * point: this is the one render that has a URL to read, and it must land
     * after hydration so React writes the highlight out. Runs once, on mount. */
    const urlTab = resolveTab(readParam('tab'));
    if (urlTab !== 'today') setTabState(urlTab);
    const sourceFile = readParam('brief');
    if (sourceFile) setBrief({ sourceFile, runDate: readParam('briefDate') });
    if (readParam('view') === 'briefs') setView('briefs');
    /* eslint-enable react-hooks/set-state-in-effect */
  }, []);

  // Cross-link focus targets handed to the destination tabs.
  const [consensusFocusCcy, setConsensusFocusCcy] = useState<string | null>(null);
  const [eventFocus, setEventFocus] = useState<{ externalId?: string | null; name: string | null } | null>(
    null
  );

  const setTab = useCallback(
    (next: TwelveXTab) => {
      setTabState(next);
      setView(null);
      syncUrl(next, brief, null);
    },
    [brief]
  );

  const openBrief = useCallback(
    (sourceFile: string, runDate: string | null) => {
      const next = { sourceFile, runDate };
      setBrief(next);
      syncUrl(tab, next, view);
    },
    [tab, view]
  );

  const closeBrief = useCallback(() => {
    setBrief(null);
    syncUrl(tab, null, view);
  }, [tab, view]);

  const openBriefsIndex = useCallback(() => {
    setView('briefs');
    syncUrl(tab, brief, 'briefs');
  }, [tab, brief]);

  const closeBriefsIndex = useCallback(() => {
    setView(null);
    syncUrl(tab, brief, null);
  }, [tab, brief]);

  // Cross-surface navigation (removed: drillToProvenance — Intelligence merged into Consensus drilldown)

  useEffect(() => {
    if (!configured) return;
    let cancelled = false;
    (async () => {
      try {
        const [
          digest,
          consensusSeries,
          intelligence,
          upcomingEvents,
          matrix,
          researchBriefs,
          ideaEval,
          consensusEval,
          tradeIdeaArchive,
        ] = await Promise.all([
          getLatestDigest(),
          getConsensusTimeSeries(),
          getIntelligence(),
          getUpcomingEvents(),
          getMatrix(),
          getBriefs(30),
          getIdeaEval(),
          getConsensusEval(),
          getTradeIdeaArchive(),
        ]);
        const opinionsDate = intelligence[0]?.run_date ?? digest?.run_date ?? null;
        const intelRunDate = intelligence[0]?.run_date ?? undefined;
        const [eventOpinions, intelligenceWhy] = await Promise.all([
          opinionsDate ? getEventOpinions(opinionsDate) : Promise.resolve([]),
          getIntelligenceWhy(intelRunDate),
        ]);
        const canonical = intelligence[0]?.run_date ?? digest?.run_date ?? null;
        const [tradeIdeas, tradeIdeaHistory, todayBriefs, todayEvents, divergenceByCurrency] = canonical
          ? await Promise.all([
              getTradeIdeas(canonical),
              getTradeIdeaHistory(45, canonical),
              getTodayBriefs(canonical),
              getTodayEvents(),
              getConsensusDivergence(canonical),
            ])
          : [[], [], [], await getTodayEvents(), {}];
        if (cancelled) return;
        const latestConsensus = selectLatestCompleteConsensus(consensusSeries);
        setData({
          digest,
          consensusSeries,
          latestConsensus,
          intelligence,
          intelligenceWhy,
          upcomingEvents,
          eventOpinions,
          matrix,
          tradeIdeas,
          tradeIdeaHistory,
          todayBriefs,
          todayEvents,
          researchBriefs,
          divergenceByCurrency,
          ideaEval,
          consensusEval,
          tradeIdeaArchive,
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

  const watchlist = useWatchlist();

  // The shared cross-surface navigator handed to every tab via context.
  const crossLink = useCallback(
    (l: CrossLink) => {
      switch (l.kind) {
        case 'currency':
          setTabState('consensus');
          setConsensusFocusCcy(l.currency);
          syncUrl('consensus', brief, view);
          break;
        case 'brief':
          openBrief(l.sourceFile, l.runDate);
          break;
        case 'event':
          setTabState('events');
          setEventFocus({ externalId: l.externalId ?? null, name: l.eventName });
          syncUrl('events', brief, view);
          break;
        case 'tab':
          setTab(l.tab);
          break;
      }
    },
    [brief, view, openBrief, setTab]
  );

  const ctx = useMemo<TwelveXContextValue>(
    () => ({ runDate: canonicalRunDate, crossLink, openBrief, watchlist }),
    [canonicalRunDate, crossLink, openBrief, watchlist]
  );

  // How-it-works is fully static and must stay reachable while the feed loads
  // or is down; the data tabs degrade to the skeleton / unavailable state
  // inside the workspace chrome instead of replacing it.
  const renderActiveTab = () => {
    if (tab === 'how-it-works') return <HowItWorksTab />;
    if (loading) return <PageSkeleton bare />;
    if (error) return <TwelveXUnavailable configured={error !== 'unconfigured'} />;
    switch (tab) {
      case 'consensus':
        return (
          <ConsensusTab
            series={data?.consensusSeries ?? []}
            latest={data?.latestConsensus ?? []}
            latestDate={latestConsensusDate}
            deltas={consensusDeltas}
            divergenceByCurrency={data?.divergenceByCurrency ?? {}}
            focusCcy={consensusFocusCcy}
            intelligenceWhy={data?.intelligenceWhy ?? { runDate: null, items: [] }}
            researchBriefs={data?.researchBriefs ?? []}
          />
        );
      case 'trades':
        return (
          <TradesTab
            ideas={data?.tradeIdeaArchive ?? []}
            ideaEval={data?.ideaEval ?? []}
            consensusEval={data?.consensusEval ?? []}
          />
        );
      case 'events':
        return (
          <EventsTab
            events={data?.upcomingEvents ?? []}
            opinions={data?.eventOpinions ?? []}
            runDate={eventOpinionsDate}
            focus={eventFocus}
            onOpenBrief={openBrief}
          />
        );
      case 'matrix':
        return <MatrixTab cells={data?.matrix ?? []} onOpenBrief={openBrief} />;
      default:
        return view === 'briefs' ? (
          <BriefsIndex
            briefs={data?.researchBriefs ?? []}
            defaultDate={canonicalRunDate}
            onBack={closeBriefsIndex}
          />
        ) : (
          <TodayTab
            digest={data?.digest ?? null}
            tradeIdeas={data?.tradeIdeas ?? []}
            tradeIdeaHistory={data?.tradeIdeaHistory ?? []}
            confluence={data?.intelligence ?? []}
            briefs={data?.todayBriefs ?? []}
            events={data?.todayEvents ?? []}
            series={data?.consensusSeries ?? []}
            divergenceByCurrency={data?.divergenceByCurrency ?? {}}
            onSeeAllBriefs={openBriefsIndex}
          />
        );
    }
  };

  return (
    <div data-testid="twelvex-workspace" className="flex min-h-full flex-col">
      <TwelveXHeading />
      <TwelveXTabBar active={tab} onSelect={setTab} />

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
