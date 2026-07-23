'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  CalendarClock,
  CalendarDays,
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
  getConsensusTimeSeries,
  getEventOpinions,
  getIntelligence,
  getIntelligenceWhy,
  getLatestDigest,
  getMatrix,
  getTradeIdeas,
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
  FxConsensusSnapshotRow,
  FxEconomicCalendarRow,
  FxEventSnapshotRow,
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
import BriefPanel from './BriefPanel';
import TwelveXHeading from './TwelveXHeading';
import { TwelveXProvider, type TwelveXContextValue, type CrossLink, type TwelveXTab } from './context';
import { useWatchlist } from './useWatchlist';

type DigestData = Awaited<ReturnType<typeof getLatestDigest>>;

/** The workspace tab bar, in display order: id, icon, and label. */
export const TWELVE_X_TABS: ReadonlyArray<{ id: TwelveXTab; Icon: typeof CalendarClock; label: string }> = [
  { id: 'today', Icon: CalendarClock, label: 'Today' },
  { id: 'consensus', Icon: LineChartIcon, label: 'Consensus' },
  { id: 'matrix', Icon: Grid3x3, label: 'Matrix' },
  { id: 'events', Icon: CalendarDays, label: 'Events' },
  { id: 'how-it-works', Icon: Workflow, label: 'How it works' },
];

/**
 * The workspace command band. `TwelveXHeading` is shared with the route's
 * Suspense fallback so the static export prerenders the h1; the right rail is
 * the canonical dl fact grid (as-of run + coverage).
 */
function TwelveXCommandBand({ runDate }: { runDate: string | null }) {
  return (
    <div className={`${SUBPAGE_MAX} pt-4 md:pt-6`}>
      <header
        data-testid="twelvex-command-band"
        className="grid gap-4 border border-hair bg-surface px-4 py-4 md:px-6 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end"
      >
        <TwelveXHeading />
        <dl className="grid grid-cols-2 gap-px border border-hair bg-hair text-sm lg:min-w-64">
          <div className="bg-surface px-3 py-2">
            <dt className="font-mono text-xs uppercase text-ink-mute">As of</dt>
            <dd className="mt-1 font-mono font-medium text-ink">{runDate ?? '—'}</dd>
          </div>
          <div className="bg-surface px-3 py-2">
            <dt className="font-mono text-xs uppercase text-ink-mute">Coverage</dt>
            <dd className="mt-1 font-medium text-ink">G10 FX</dd>
          </div>
        </dl>
      </header>
    </div>
  );
}

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
              className="mt-5 inline-flex items-center rounded-lg border border-hair px-4 py-2 text-sm font-medium text-accent transition-colors hover:bg-ink/[0.06]"
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
  todayBriefs: FxBriefRow[];
  todayEvents: FxEconomicCalendarRow[];
  researchBriefs: FxBriefRow[];
}

export function resolveTab(urlTab: string | null): TwelveXTab {
  if (urlTab === 'consensus') return 'consensus';
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

  // In-page navigation state — local, seeded once from the URL for deep links.
  const [tab, setTabState] = useState<TwelveXTab>(() => resolveTab(readParam('tab')));
  const [brief, setBrief] = useState<BriefTarget | null>(() => {
    const sf = readParam('brief');
    return sf ? { sourceFile: sf, runDate: readParam('briefDate') } : null;
  });
  const [view, setView] = useState<'briefs' | null>(() =>
    readParam('view') === 'briefs' ? 'briefs' : null,
  );

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
        ] = await Promise.all([
          getLatestDigest(),
          getConsensusTimeSeries(),
          getIntelligence(),
          getUpcomingEvents(),
          getMatrix(),
          getBriefs(14),
        ]);
        const opinionsDate = intelligence[0]?.run_date ?? digest?.run_date ?? null;
        const intelRunDate = intelligence[0]?.run_date ?? undefined;
        const [eventOpinions, intelligenceWhy] = await Promise.all([
          opinionsDate ? getEventOpinions(opinionsDate) : Promise.resolve([]),
          getIntelligenceWhy(intelRunDate),
        ]);
        const canonical = intelligence[0]?.run_date ?? digest?.run_date ?? null;
        const [tradeIdeas, todayBriefs, todayEvents] = canonical
          ? await Promise.all([getTradeIdeas(canonical), getTodayBriefs(canonical), getTodayEvents()])
          : [[], [], await getTodayEvents()];
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
          todayBriefs,
          todayEvents,
          researchBriefs,
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
            focusCcy={consensusFocusCcy}
            intelligenceWhy={data?.intelligenceWhy ?? { runDate: null, items: [] }}
            researchBriefs={data?.researchBriefs ?? []}
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
          <BriefsIndex briefs={data?.todayBriefs ?? []} onBack={closeBriefsIndex} />
        ) : (
          <TodayTab
            digest={data?.digest ?? null}
            tradeIdeas={data?.tradeIdeas ?? []}
            confluence={data?.intelligence ?? []}
            briefs={data?.todayBriefs ?? []}
            events={data?.todayEvents ?? []}
            series={data?.consensusSeries ?? []}
            onSeeAllBriefs={openBriefsIndex}
          />
        );
    }
  };

  return (
    <div data-testid="twelvex-workspace" className="flex min-h-full flex-col">
      <TwelveXCommandBand runDate={canonicalRunDate} />
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
