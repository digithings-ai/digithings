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
import { EmptyState } from '@digithings/ui';
import { Button } from '@digithings/ui/ui';

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
import { netCarriedIdeas } from '@/lib/twelve-x/trade-history';
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
import IdeaCardsIndex from './IdeaCardsIndex';
import IdeaPanel from './IdeaPanel';
import ConsensusTab from './ConsensusTab';
import EventsTab from './EventsTab';
import HowItWorksTab from './HowItWorksTab';
import MatrixTab from './MatrixTab';
import TradesTab from './TradesTab';
import TrackRecordTab from './TrackRecordTab';
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
            configured ? (
              <Button
                type="button"
                variant="outline"
                onClick={() => window.location.reload()}
                className="mt-5 h-auto items-center border-hair px-4 py-2 text-sm font-medium text-accent transition-colors hover:bg-ink/[0.06]"
              >
                Retry
              </Button>
            ) : undefined
          }
        />
      </div>
    </div>
  );
}

/** A brief drill-down target: the source_file key plus the run that owns it. */
export type BriefTarget = { sourceFile: string; runDate: string | null };

/** A trade-idea drill-down target: the board that published it plus its rank. */
export type IdeaTarget = { runDate: string; rank: number };

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
  /** Raw (un-netted) eval rows for the track-record tab's honest carried count. */
  ideaEvalRaw: FxIdeaEvalRow[];
  consensusEval: FxConsensusEvalRow[];
}

export function resolveTab(urlTab: string | null): TwelveXTab {
  if (urlTab === 'consensus') return 'consensus';
  if (urlTab === 'trades') return 'trades';
  if (urlTab === 'track-record') return 'track-record';
  if (urlTab === 'intelligence') return 'consensus'; // Legacy redirect
  if (urlTab === 'events') return 'events';
  if (urlTab === 'matrix') return 'matrix';
  if (urlTab === 'how-it-works') return 'how-it-works';
  return 'today';
}

/** Read a query param from the live URL — client only, and only after mount. */
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
  view: 'briefs' | 'ideas' | null = null,
  idea: IdeaTarget | null = null,
): void {
  if (typeof window === 'undefined') return;
  const p = new URLSearchParams();
  if (tab !== 'today') p.set('tab', tab);
  if (brief?.sourceFile) {
    p.set('brief', brief.sourceFile);
    if (brief.runDate) p.set('briefDate', brief.runDate);
  }
  if (view) p.set('view', view);
  if (idea) {
    p.set('idea', idea.runDate);
    p.set('ideaRank', String(idea.rank));
  }
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
  const [view, setView] = useState<'briefs' | 'ideas' | null>(null);
  const [idea, setIdea] = useState<IdeaTarget | null>(null);

  useEffect(() => {
    /* eslint-disable react-hooks/set-state-in-effect -- the cascade is the
     * point: this is the one render that has a URL to read, and it must land
     * after hydration so React writes the highlight out. Runs once, on mount. */
    const urlTab = resolveTab(readParam('tab'));
    if (urlTab !== 'today') setTabState(urlTab);
    const sourceFile = readParam('brief');
    if (sourceFile) setBrief({ sourceFile, runDate: readParam('briefDate') });
    if (readParam('view') === 'briefs') setView('briefs');
    if (readParam('view') === 'ideas') setView('ideas');
    const ideaRunDate = readParam('idea');
    const ideaRank = Number(readParam('ideaRank'));
    if (ideaRunDate && Number.isInteger(ideaRank) && ideaRank > 0) {
      setIdea({ runDate: ideaRunDate, rank: ideaRank });
    }
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
      syncUrl(next, brief, null, idea);
    },
    [brief, idea]
  );

  const openBrief = useCallback(
    (sourceFile: string, runDate: string | null) => {
      const next = { sourceFile, runDate };
      setBrief(next);
      syncUrl(tab, next, view, idea);
    },
    [tab, view, idea]
  );

  const closeBrief = useCallback(() => {
    setBrief(null);
    syncUrl(tab, null, view, idea);
  }, [tab, view, idea]);

  const openBriefsIndex = useCallback(() => {
    setView('briefs');
    syncUrl(tab, brief, 'briefs', idea);
  }, [tab, brief, idea]);

  const closeBriefsIndex = useCallback(() => {
    setView(null);
    syncUrl(tab, brief, null, idea);
  }, [tab, brief, idea]);

  const openIdea = useCallback(
    (runDate: string, rank: number) => {
      const next = { runDate, rank };
      setIdea(next);
      syncUrl(tab, brief, view, next);
    },
    [tab, brief, view]
  );

  const closeIdea = useCallback(() => {
    setIdea(null);
    syncUrl(tab, brief, view, null);
  }, [tab, brief, view]);

  const openIdeasIndex = useCallback(() => {
    setView('ideas');
    syncUrl(tab, brief, 'ideas', idea);
  }, [tab, brief, idea]);

  const closeIdeasIndex = useCallback(() => {
    setView(null);
    syncUrl(tab, brief, null, idea);
  }, [tab, brief, idea]);

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
          ideaEvalRaw,
          consensusEval,
          tradeIdeaArchive,
        ] = await Promise.all([
          getLatestDigest(),
          getConsensusTimeSeries(),
          getIntelligence(),
          getUpcomingEvents(),
          getMatrix(),
          getBriefs(30),
          getIdeaEval({ netCarried: false }),
          getConsensusEval(),
          getTradeIdeaArchive(),
        ]);
        // The raw rows are a superset: net the carried boards locally so the
        // page fetches fx_idea_eval once instead of twice.
        const ideaEval = netCarriedIdeas(ideaEvalRaw);
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
          ideaEvalRaw,
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
          syncUrl('consensus', brief, view, idea);
          break;
        case 'brief':
          openBrief(l.sourceFile, l.runDate);
          break;
        case 'event':
          setTabState('events');
          setEventFocus({ externalId: l.externalId ?? null, name: l.eventName });
          syncUrl('events', brief, view, idea);
          break;
        case 'ideas':
          setTabState('today');
          setView('ideas');
          syncUrl('today', brief, 'ideas', idea);
          break;
        case 'tab':
          setTab(l.tab);
          break;
      }
    },
    [brief, view, idea, openBrief, setTab]
  );

  const ctx = useMemo<TwelveXContextValue>(
    () => ({ runDate: canonicalRunDate, crossLink, openBrief, openIdea, watchlist }),
    [canonicalRunDate, crossLink, openBrief, openIdea, watchlist]
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
            onOpenIdea={openIdea}
          />
        );
      case 'track-record':
        return (
          <TrackRecordTab
            ideas={data?.tradeIdeaArchive ?? []}
            ideaEvalRaw={data?.ideaEvalRaw ?? []}
            consensusEval={data?.consensusEval ?? []}
            divergenceByCurrency={data?.divergenceByCurrency ?? {}}
            series={data?.consensusSeries ?? []}
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
        return view === 'ideas' ? (
          <IdeaCardsIndex
            ideas={data?.tradeIdeaArchive ?? []}
            ideaEval={data?.ideaEval ?? []}
            onBack={closeIdeasIndex}
          />
        ) : view === 'briefs' ? (
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

        {/* Slide-over trade-idea panel — same chrome, lifecycle detail. */}
        <IdeaPanel
          open={!!idea}
          runDate={idea?.runDate ?? null}
          rank={idea?.rank ?? null}
          ideas={data?.tradeIdeaArchive ?? []}
          ideaEval={data?.ideaEval ?? []}
          loading={loading}
          error={error}
          onClose={closeIdea}
        />
      </TwelveXProvider>
    </div>
  );
}
