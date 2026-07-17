'use client';

import { useMemo } from 'react';
import { Layers, Users, CalendarClock } from 'lucide-react';
import type {
  FxConfluenceSnapshotRow,
  FxEventSnapshotRow,
  IntelligenceWhy,
  IntelligenceWhyItem,
} from '@/lib/twelve-x/types';
import { resolveCatalyst } from '@/lib/twelve-x/fetch';
import { useTwelveX } from './context';
import IntelligenceWhyPanel from './IntelligenceWhyPanel';

/** Map a confluence direction/lean string to a P&L text color class. */
function directionColorClass(direction: string): string {
  const d = direction.trim().toLowerCase();
  if (d === 'bullish' || d === 'long' || d === 'buy') return 'text-up';
  if (d === 'bearish' || d === 'short' || d === 'sell') return 'text-down';
  if (d === 'watch') return 'text-warn';
  return 'text-ink-soft';
}

function directionLabel(direction: string): string {
  const d = direction.trim();
  if (!d) return '—';
  return d.charAt(0).toUpperCase() + d.slice(1).toLowerCase();
}

function asNumber(v: unknown): number | null {
  const n = typeof v === 'number' ? v : Number(v);
  return Number.isFinite(n) ? n : null;
}

function asComponents(raw: unknown): Record<string, number> {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return {};
  const out: Record<string, number> = {};
  for (const [k, v] of Object.entries(raw as Record<string, unknown>)) {
    const n = asNumber(v);
    if (n != null) out[k] = n;
  }
  return out;
}

function asStringList(raw: unknown): string[] {
  if (Array.isArray(raw)) return raw.map((x) => String(x)).filter((s) => s.trim().length > 0);
  return [];
}

function IntelligenceCard({
  idea,
  events,
  whyItem,
  initialExpanded,
  focused,
}: {
  idea: FxConfluenceSnapshotRow;
  events: FxEventSnapshotRow[];
  whyItem: IntelligenceWhyItem | null;
  initialExpanded?: boolean;
  /** Cross-link target: highlight + auto-expand this card's why-panel. */
  focused?: boolean;
}) {
  const { crossLink } = useTwelveX();
  const colorClass = directionColorClass(idea.direction);
  const components = useMemo(() => asComponents(idea.components), [idea.components]);
  // brief_keys holds the SUPPORTING DESK names behind this idea (broker names,
  // not source_file document keys). When the richer Tier-3 "why" panel is
  // present (assembled from the relevance ledger), it supersedes this flat list;
  // we only fall back to brief_keys when no why-item matched this idea.
  const supportingDesks = useMemo(() => asStringList(idea.brief_keys), [idea.brief_keys]);
  const nBrokers = asNumber(components.n_brokers);
  const catalyst = useMemo(() => resolveCatalyst(idea, events), [idea, events]);
  const daysToCatalyst = catalyst.daysToCatalyst;
  // A heuristic (non-explicit) catalyst match leaves eventKey null — hedge the
  // wording so we don't overstate the link.
  const hedged = catalyst.eventName != null && catalyst.eventKey == null;

  return (
    <div
      data-focus-ccy={focused ? idea.currency : undefined}
      className={`glass-card flex flex-col gap-3 p-4${focused ? ' ring-2 ring-accent' : ''}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <span className="shrink-0 rounded border border-hair bg-ink/[0.06] px-1.5 py-0.5 font-mono text-[10px] text-ink-mute">
            #{idea.rank}
          </span>
          <button
            type="button"
            onClick={() => crossLink({ kind: 'currency', currency: idea.currency })}
            className="truncate font-mono text-sm font-semibold text-ink hover:text-accent hover:underline transition-colors"
            title={`See ${idea.currency} consensus`}
          >
            {idea.currency}
          </button>
        </div>
        <span className={`shrink-0 text-xs font-semibold ${colorClass}`}>
          {directionLabel(idea.direction)}
        </span>
      </div>

      <p className="text-sm leading-snug text-ink">{idea.title}</p>

      <div className="flex items-center justify-between pt-0.5">
        <span className="text-[11px] uppercase tracking-wider text-ink-mute">Confluence score</span>
        <span className={`qn-metric tabular-nums ${colorClass}`}>
          {Number.isFinite(idea.score) ? idea.score.toFixed(2) : '—'}
        </span>
      </div>

      {/* The [0,1] score legs (consensus / event / breadth) are NOT shown on the
          card face — a first-time reader can't parse three bars in 5s. They live
          in the "Why" panel's Tier-1 waterfall (progressive disclosure). */}

      {(nBrokers != null || daysToCatalyst != null || catalyst.eventName != null || supportingDesks.length > 0) ? (
        <div className="mt-auto flex flex-col gap-1.5 border-t border-hair/60 pt-2 text-[11px] text-ink-mute">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
            {nBrokers != null ? (
              <span className="flex items-center gap-1.5">
                <Users size={12} aria-hidden />
                <span className="qn-metric tabular-nums text-ink-soft">{nBrokers}</span>
                desks
              </span>
            ) : null}
            {daysToCatalyst != null ? (
              <span className="flex items-center gap-1.5">
                <CalendarClock size={12} aria-hidden />
                <span className="qn-metric tabular-nums text-ink-soft">
                  {hedged ? '~' : ''}
                  {daysToCatalyst}
                </span>
                {daysToCatalyst === 1 ? 'day to catalyst' : 'days to catalyst'}
              </span>
            ) : catalyst.eventName != null ? (
              <span className="flex items-center gap-1.5">
                <CalendarClock size={12} aria-hidden />
                {hedged ? 'likely catalyst' : 'catalyst'}
              </span>
            ) : null}
            {catalyst.eventName != null ? (
              <button
                type="button"
                onClick={() =>
                  crossLink({
                    kind: 'event',
                    eventName: catalyst.eventName,
                    externalId: catalyst.calendarExternalId,
                  })
                }
                className="max-w-full truncate font-medium text-accent hover:underline"
                title={`${hedged ? 'Likely catalyst: ' : 'Catalyst: '}${catalyst.eventName}`}
              >
                {hedged ? '~' : ''}
                {catalyst.eventName}
              </button>
            ) : null}
          </div>
          {whyItem == null && supportingDesks.length > 0 ? (
            <p className="truncate text-ink-mute" title={supportingDesks.join(', ')}>
              <span className="text-ink-soft">Desks:</span> {supportingDesks.join(', ')}
            </p>
          ) : null}
        </div>
      ) : null}

      {whyItem ? <IntelligenceWhyPanel item={whyItem} initialExpanded={initialExpanded || focused} /> : null}
    </div>
  );
}

export default function IntelligenceTab({
  confluence,
  runDate,
  events,
  why,
  initialExpanded,
  focusCcy,
}: {
  confluence: FxConfluenceSnapshotRow[];
  runDate: string | null;
  events: FxEventSnapshotRow[];
  why: IntelligenceWhy;
  /** Start every card's why-panel expanded (deterministic SSR / tests). */
  initialExpanded?: boolean;
  /** Cross-link focus (e.g. from Consensus "Why this weight?") — auto-expands
   *  and highlights the matching currency's card. */
  focusCcy?: string | null;
}) {
  const focusUpper = focusCcy ? focusCcy.toUpperCase() : null;
  // Index assembled why-items by rank (1:1 with confluence rank) and by base
  // currency, so a card resolves its drill-down even if ranks ever diverge.
  const whyByRank = useMemo(() => {
    const m = new Map<number, IntelligenceWhyItem>();
    for (const it of why.items) m.set(it.rank, it);
    return m;
  }, [why.items]);
  const whyByCurrency = useMemo(() => {
    const m = new Map<string, IntelligenceWhyItem>();
    for (const it of why.items) m.set(it.currency.toUpperCase(), it);
    return m;
  }, [why.items]);

  const whyFor = (idea: FxConfluenceSnapshotRow): IntelligenceWhyItem | null =>
    whyByRank.get(idea.rank) ?? whyByCurrency.get(idea.currency.toUpperCase()) ?? null;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3 px-1">
        <Layers size={18} className="shrink-0 text-accent" aria-hidden />
        <h2 className="font-display text-2xl tracking-tight text-ink">
          Confluence trade ideas
        </h2>
        {runDate ? (
          <span className="ml-auto font-mono text-[10px] text-ink-mute">{runDate}</span>
        ) : null}
      </div>

      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 px-1">
        <p className="max-w-2xl text-xs text-ink-mute">
          Ranked directional reads where a cross-desk consensus meets a near-term catalyst. Each
          card leads with the call; open <span className="font-medium text-ink-soft">Why</span> for
          the score breakdown, the consensus behind it and the supporting desks.
        </p>
        <span className="font-mono text-[10px] text-ink-mute">score 0–1 · higher = stronger</span>
      </div>

      {confluence.length > 0 ? (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {confluence.map((idea) => (
            <IntelligenceCard
              key={`${idea.run_date}-${idea.rank}`}
              idea={idea}
              events={events}
              whyItem={whyFor(idea)}
              initialExpanded={initialExpanded}
              focused={focusUpper != null && idea.currency.toUpperCase() === focusUpper}
            />
          ))}
        </div>
      ) : (
        <div className="glass-card p-10 text-center text-sm text-ink-mute">
          No confluence trade ideas{runDate ? ` for ${runDate}` : ''} yet.
        </div>
      )}
    </div>
  );
}
