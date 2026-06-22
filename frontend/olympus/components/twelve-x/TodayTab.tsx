'use client';

import type {
  FxConfluenceSnapshotRow,
  FxEconomicCalendarRow,
  FxBriefRow,
  FxTradeIdeaRow,
  ConsensusDeltaSet,
} from '@/lib/twelve-x/types';
import TradeIdeasPanel from './TradeIdeasPanel';
import DigestBrief from './DigestBrief';
import BriefsSlideshow from './BriefsSlideshow';
import EventsMiniTimeline from './EventsMiniTimeline';
import MoversStrip from './MoversStrip';
import { useTwelveX } from './context';

type DigestData = { run_date: string; summary: string; key_themes: string[]; doc_count: number; broker_count: number } | null;

export default function TodayTab({
  digest,
  tradeIdeas,
  confluence,
  deltas,
  briefs,
  events,
  onSeeAllBriefs,
}: {
  digest: DigestData;
  tradeIdeas: FxTradeIdeaRow[];
  confluence: FxConfluenceSnapshotRow[];
  deltas: ConsensusDeltaSet;
  briefs: FxBriefRow[];
  events: FxEconomicCalendarRow[];
  onSeeAllBriefs: () => void;
}) {
  const { crossLink } = useTwelveX();
  return (
    <div className="flex flex-col gap-4">
      {/* Above the fold: trade ideas + digest brief co-lead */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1.2fr_1fr]">
        <TradeIdeasPanel ideas={tradeIdeas} confluence={confluence} />
        <DigestBrief digest={digest} />
      </div>

      {/* What changed in consensus */}
      <section className="glass-card p-4">
        <header className="mb-2 flex items-baseline gap-2">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-text-secondary">What changed — consensus</h2>
          <button type="button" className="ml-auto text-[11px] text-fin-blue hover:underline" onClick={() => crossLink({ kind: 'tab', tab: 'consensus' })}>
            see more →
          </button>
        </header>
        {deltas.movers.length > 0 ? (
          <MoversStrip movers={deltas.movers} onSelect={(c) => crossLink({ kind: 'currency', currency: c })} title="" />
        ) : (
          <p className="text-sm text-text-muted">No prior run to compare yet.</p>
        )}
      </section>

      {/* Below the fold: briefs slideshow + today's events */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <BriefsSlideshow briefs={briefs} onSeeMore={onSeeAllBriefs} />
        <EventsMiniTimeline events={events} />
      </div>
    </div>
  );
}
