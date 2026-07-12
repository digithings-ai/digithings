'use client';

import { useMemo } from 'react';
import type {
  FxConfluenceSnapshotRow,
  FxConsensusSnapshotRow,
  FxEconomicCalendarRow,
  FxBriefRow,
  FxTradeIdeaRow,
} from '@/lib/twelve-x/types';
import { eventLocalDateKey } from '@/lib/twelve-x/fetch';
import TradeIdeasPanel from './TradeIdeasPanel';
import DigestBrief from './DigestBrief';
import TodayConsensusChart from './TodayConsensusChart';
import EventsTimeline, { eventsToTimeline } from './EventsTimeline';
import { useTwelveX } from './context';

type DigestData = { run_date: string; summary: string; key_themes: string[]; doc_count: number; broker_count: number } | null;

export default function TodayTab({
  digest,
  tradeIdeas,
  confluence,
  briefs,
  events,
  series,
  onSeeAllBriefs,
}: {
  digest: DigestData;
  tradeIdeas: FxTradeIdeaRow[];
  confluence: FxConfluenceSnapshotRow[];
  briefs: FxBriefRow[];
  events: FxEconomicCalendarRow[];
  series: FxConsensusSnapshotRow[];
  onSeeAllBriefs: () => void;
}) {
  const { openBrief } = useTwelveX();

  const timelineEvents = useMemo(() => eventsToTimeline(events), [events]);

  // The single day the timeline renders: the local day shared by today's
  // events, else the viewer-local "today" so an empty day still renders an axis.
  const today = useMemo(() => {
    if (events.length > 0) return eventLocalDateKey(events[0]);
    return eventLocalDateKey({ event_datetime_utc: new Date().toISOString(), event_date: '' });
  }, [events]);

  return (
    <div className="flex flex-col gap-4">
      {/* Above the fold: trade ideas + digest brief co-lead */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1.2fr_1fr]">
        <TradeIdeasPanel ideas={tradeIdeas} confluence={confluence} />
        <DigestBrief digest={digest} />
      </div>

      {/* Mid row: consensus-average chart (wider) + broker briefs, height-matched. */}
      <div className="today-mid grid grid-cols-1 items-stretch gap-4 lg:grid-cols-[1.5fr_1fr]">
        <div className="flex min-w-0 flex-col flex-1">
          <TodayConsensusChart series={series} />
        </div>

        <section className="glass-card flex min-w-0 flex-col p-4 lg:overflow-hidden">
          <header className="mb-3 flex shrink-0 items-baseline gap-2">
            <h2 className="text-[13px] font-semibold uppercase tracking-wide text-ink-soft">
              Broker briefs
            </h2>
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
            // The scroller is absolutely positioned at `lg` so the brief list never
            // inflates the grid row — the row height is driven by the consensus chart
            // column, and the briefs scroll within that matched height. On mobile
            // (stacked, single column) the list flows naturally and the page scrolls.
            <div className="min-h-0 lg:relative lg:flex-1">
              <ul className="-mx-1 flex flex-col gap-2.5 px-1 lg:absolute lg:inset-0 lg:overflow-y-auto">
                {briefs.map((b, n) => (
                  <li key={`${b.source_file}-${b.run_date}-${n}`}>
                    <button
                      type="button"
                      className="w-full rounded-lg border border-hair bg-term-bg p-3 text-left transition-colors hover:border-accent/50"
                      onClick={() => openBrief(b.source_file, b.run_date)}
                    >
                      <div className="flex items-center gap-2 text-[11px] text-ink-mute">
                        <span className="font-semibold text-ink-soft">
                          {b.broker_name ?? 'Unknown desk'}
                        </span>
                        {b.trader_relevance ? (
                          <span className="uppercase">· {b.trader_relevance}</span>
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
              </ul>
            </div>
          )}
        </section>
      </div>

      {/* Full-width single-day timeline (replaces the old compact events tile). */}
      <section className="glass-card p-4">
        <header className="mb-3 flex items-baseline gap-2">
          <h2 className="text-[13px] font-semibold uppercase tracking-wide text-ink-soft">
            Today&rsquo;s timeline
          </h2>
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
