'use client';

import { Fragment, useMemo, useState } from 'react';
import { CalendarClock } from 'lucide-react';
import type {
  FxConfluenceSnapshotRow,
  FxConsensusDivergence,
  FxConsensusSnapshotRow,
  FxEconomicCalendarRow,
  FxBriefRow,
  FxTradeIdeaRow,
} from '@/lib/twelve-x/types';
import { eventLocalDateKey } from '@/lib/twelve-x/fetch';
import { countDisputedTradeIdeas, disputedTradeIdeaRanks } from '@/lib/twelve-x/divergence';
import TradeIdeasPanel from './TradeIdeasPanel';
import DigestBrief from './DigestBrief';
import TodayConsensusChart from './TodayConsensusChart';
import EventsTimeline, { eventsToTimeline } from './EventsTimeline';
import { useTwelveX } from './context';
import { TwelveXSectionHeading } from './TwelveXSectionHeading';

type DigestData = { run_date: string; summary: string; key_themes: string[]; doc_count: number; broker_count: number } | null;

export default function TodayTab({
  digest,
  tradeIdeas,
  tradeIdeaHistory = [],
  confluence,
  briefs,
  events,
  series,
  divergenceByCurrency = {},
  onSeeAllBriefs,
}: {
  digest: DigestData;
  tradeIdeas: FxTradeIdeaRow[];
  tradeIdeaHistory?: Pick<FxTradeIdeaRow, 'run_date' | 'pair' | 'direction' | 'as_of'>[];
  confluence: FxConfluenceSnapshotRow[];
  briefs: FxBriefRow[];
  events: FxEconomicCalendarRow[];
  series: FxConsensusSnapshotRow[];
  divergenceByCurrency?: Record<string, FxConsensusDivergence>;
  onSeeAllBriefs: () => void;
}) {
  const { openBrief } = useTwelveX();
  const [highlightDisputed, setHighlightDisputed] = useState(false);

  const disputeCount = useMemo(
    () => countDisputedTradeIdeas(tradeIdeas, divergenceByCurrency),
    [tradeIdeas, divergenceByCurrency],
  );

  const highlightRanks = useMemo(() => {
    if (!highlightDisputed) return undefined;
    return new Set(disputedTradeIdeaRanks(tradeIdeas, divergenceByCurrency));
  }, [highlightDisputed, tradeIdeas, divergenceByCurrency]);

  const timelineEvents = useMemo(() => eventsToTimeline(events), [events]);

  // The single day the timeline renders: the local day shared by today's
  // events, else the viewer-local "today" so an empty day still renders an axis.
  const today = useMemo(() => {
    if (events.length > 0) return eventLocalDateKey(events[0]);
    return eventLocalDateKey({ event_datetime_utc: new Date().toISOString(), event_date: '' });
  }, [events]);

  const briefDateGroups = useMemo(() => {
    // Group briefs by effective date (report_date ?? run_date), newest first.
    const grouped = new Map<string, FxBriefRow[]>();
    briefs.forEach((b) => {
      const effDate = b.report_date ?? b.run_date;
      if (!grouped.has(effDate)) grouped.set(effDate, []);
      grouped.get(effDate)!.push(b);
    });
    return Array.from(grouped.keys())
      .sort()
      .reverse()
      .map((dateKey) => ({ dateKey, dateBriefs: grouped.get(dateKey)! }));
  }, [briefs]);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3 px-1">
        <CalendarClock size={18} className="shrink-0 text-accent" aria-hidden />
        <h2 className="font-display text-2xl tracking-tight text-ink">Today&rsquo;s read</h2>
      </div>

      {disputeCount > 0 ? (
        <p className="px-1 text-sm text-ink-soft">
          <button
            type="button"
            data-disputes-line="true"
            className="text-left text-accent hover:underline"
            onClick={() => setHighlightDisputed((v) => !v)}
          >
            The data disputes {disputeCount} of today&rsquo;s calls
            {disputeCount === 1 ? '' : 's'}.
          </button>
        </p>
      ) : null}

      {/* Left stack (digest → ideas → consensus) + wider briefs rail, height-matched. */}
      <div className="today-main grid grid-cols-1 items-start gap-4 lg:grid-cols-[minmax(0,0.95fr)_minmax(0,1.25fr)]">
        <div className="flex min-w-0 flex-col gap-4">
          <DigestBrief digest={digest} />
          <TradeIdeasPanel
            ideas={tradeIdeas}
            ideaHistory={tradeIdeaHistory}
            confluence={confluence}
            highlightRanks={highlightRanks}
          />
          <TodayConsensusChart series={series} />
        </div>

        <div className="min-w-0 lg:relative lg:self-stretch">
          <section className="glass-card flex max-h-[32rem] min-h-[28rem] min-w-0 flex-col overflow-hidden p-4 lg:absolute lg:inset-0 lg:max-h-none lg:min-h-0">
            <header className="mb-3 flex shrink-0 items-baseline gap-2">
              <TwelveXSectionHeading>Broker briefs</TwelveXSectionHeading>
              <span className="ml-auto font-mono text-[10px] text-ink-mute">
                {briefs.length} {briefs.length === 1 ? 'brief' : 'briefs'}
              </span>
              {briefs.length > 0 ? (
                <button
                  type="button"
                  className="text-[11px] text-accent hover:underline"
                  onClick={onSeeAllBriefs}
                >
                  see all →
                </button>
              ) : null}
            </header>

            {briefs.length === 0 ? (
              <p className="text-sm text-ink-mute">No research briefs for today yet.</p>
            ) : (
              <div
                className="min-h-0 flex-1 overflow-y-auto overscroll-contain pr-1"
                aria-label="Broker brief cards"
                tabIndex={0}
              >
                {/*
                  One gap source for the whole list. Date headers and cards share
                  the same flex gap so cross-date rows do not pick up stacked
                  space-y + heading margin + inner gap (the intermittent "huge
                  gap between cards" on mobile when briefs span multiple dates).
                */}
                <ul className="flex flex-col gap-2">
                  {briefDateGroups.map(({ dateKey, dateBriefs }) => (
                    <Fragment key={dateKey}>
                      <li className="shrink-0">
                        <h3 className="font-mono text-[10.5px] font-semibold uppercase tracking-wide text-ink-soft">
                          {dateKey}
                        </h3>
                      </li>
                      {dateBriefs.map((b, n) => (
                        <li key={`${b.source_file}-${b.run_date}-${n}`} className="shrink-0">
                          <button
                            type="button"
                            className="w-full rounded-lg border border-hair bg-term-bg p-3 text-left transition-colors hover:border-accent/50"
                            onClick={() => openBrief(b.source_file, b.run_date)}
                          >
                            <div className="flex min-w-0 items-center gap-2 text-[11px] text-ink-mute">
                              <span className="min-w-0 truncate font-semibold text-ink-soft">
                                {b.broker_name ?? 'Unknown desk'}
                              </span>
                              {b.trader_relevance ? (
                                <span className="shrink-0 uppercase">· {b.trader_relevance}</span>
                              ) : null}
                            </div>
                            <p className="mt-1 truncate text-sm font-medium text-ink">
                              {b.document_title ?? b.source_file}
                            </p>
                            {b.central_thesis ? (
                              <p className="mt-1 line-clamp-2 text-xs text-ink-soft">
                                {b.central_thesis}
                              </p>
                            ) : null}
                          </button>
                        </li>
                      ))}
                    </Fragment>
                  ))}
                </ul>
              </div>
            )}
          </section>
        </div>
      </div>

      {/* Full-width single-day timeline (replaces the old compact events tile). */}
      <section className="glass-card p-4">
        <header className="mb-3 flex items-baseline gap-2">
          <TwelveXSectionHeading>Today&rsquo;s timeline</TwelveXSectionHeading>
          <span className="ml-auto font-mono text-[10px] text-ink-mute">00:00 – 24:00</span>
        </header>
        {timelineEvents.length === 0 ? (
          <p className="text-sm text-ink-mute">No macro events scheduled today.</p>
        ) : (
          <EventsTimeline events={timelineEvents} mode="single" day={today} />
        )}
      </section>
    </div>
  );
}
