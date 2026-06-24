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

/** Map a confluence direction/lean string to a .fin-* text color class. */
function directionColorClass(direction: string): string {
  const d = direction.trim().toLowerCase();
  if (d === 'bullish' || d === 'long' || d === 'buy') return 'text-fin-green';
  if (d === 'bearish' || d === 'short' || d === 'sell') return 'text-fin-red';
  if (d === 'watch') return 'text-fin-amber';
  return 'text-text-secondary';
}

function directionLabel(direction: string): string {
  const d = direction.trim();
  if (!d) return '—';
  return d.charAt(0).toUpperCase() + d.slice(1).toLowerCase();
}

/**
 * The three [0,1] score-contributing components from `build_confluence`, in
 * legend order. `recency`, `n_brokers`, `days_to_catalyst` are metadata,
 * surfaced as labels rather than score legs.
 */
const COMPONENT_SEGMENTS = [
  { key: 'consensus_strength', label: 'Consensus', color: '#3B82F6' },
  { key: 'event_alignment', label: 'Event', color: '#10B981' },
  { key: 'breadth', label: 'Breadth', color: '#8B5CF6' },
] as const;

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

function clamp01(v: number): number {
  return Math.max(0, Math.min(1, Number.isFinite(v) ? v : 0));
}

/**
 * The three [0,1] score legs, each shown as its OWN magnitude fill against full
 * weight (1.0) — NOT normalized to their sum. So a leg of 0.8 reads as a track
 * that is 80% full regardless of the other legs, making each contribution's
 * absolute strength legible. Legs at ≈0 still
 * render their (empty) track so a weak leg reads as weak, not missing.
 */
function ComponentBar({ components }: { components: Record<string, number> }) {
  const segments = COMPONENT_SEGMENTS.map((s) => ({
    ...s,
    value: clamp01(components[s.key] ?? 0),
  }));

  return (
    <div className="space-y-1.5">
      <div className="flex h-2 w-full gap-1">
        {segments.map((s) => (
          <div
            key={s.key}
            className="relative h-full flex-1 overflow-hidden rounded-full bg-white/[0.06]"
            title={`${s.label}: ${s.value.toFixed(2)}`}
          >
            <div
              className="absolute inset-y-0 left-0 rounded-full"
              style={{ width: `${s.value * 100}%`, backgroundColor: s.color }}
            />
          </div>
        ))}
      </div>
      <div className="flex flex-wrap gap-x-3 gap-y-0.5">
        {segments.map((s) => (
          <span key={s.key} className="flex items-center gap-1 text-[10px] text-text-muted">
            <span className="inline-block h-2 w-2 rounded-sm" style={{ backgroundColor: s.color }} />
            {s.label}
            <span className="tabular-nums text-text-secondary">{s.value.toFixed(2)}</span>
          </span>
        ))}
      </div>
    </div>
  );
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
      className={`glass-card flex flex-col gap-3 p-4${focused ? ' ring-2 ring-fin-blue' : ''}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <span className="shrink-0 rounded border border-border-subtle bg-white/[0.06] px-1.5 py-0.5 font-mono text-[10px] text-text-muted">
            #{idea.rank}
          </span>
          <button
            type="button"
            onClick={() => crossLink({ kind: 'currency', currency: idea.currency })}
            className="truncate font-mono text-sm font-semibold text-text-primary hover:text-fin-blue hover:underline transition-colors"
            title={`See ${idea.currency} consensus`}
          >
            {idea.currency}
          </button>
        </div>
        <span className={`shrink-0 text-xs font-semibold ${colorClass}`}>
          {directionLabel(idea.direction)}
        </span>
      </div>

      <p className="text-sm leading-snug text-text-primary">{idea.title}</p>

      <div className="flex items-center justify-between pt-0.5">
        <span className="text-[11px] uppercase tracking-wider text-text-muted">Confluence score</span>
        <span className={`qn-metric tabular-nums ${colorClass}`}>
          {Number.isFinite(idea.score) ? idea.score.toFixed(2) : '—'}
        </span>
      </div>

      {Object.keys(components).length > 0 ? <ComponentBar components={components} /> : null}

      {(nBrokers != null || daysToCatalyst != null || catalyst.eventName != null || supportingDesks.length > 0) ? (
        <div className="mt-auto flex flex-col gap-1.5 border-t border-border-subtle/60 pt-2 text-[11px] text-text-muted">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
            {nBrokers != null ? (
              <span className="flex items-center gap-1.5">
                <Users size={12} aria-hidden />
                <span className="qn-metric tabular-nums text-text-secondary">{nBrokers}</span>
                desks
              </span>
            ) : null}
            {daysToCatalyst != null ? (
              <span className="flex items-center gap-1.5">
                <CalendarClock size={12} aria-hidden />
                <span className="qn-metric tabular-nums text-text-secondary">
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
                className="max-w-full truncate font-medium text-fin-blue hover:underline"
                title={`${hedged ? 'Likely catalyst: ' : 'Catalyst: '}${catalyst.eventName}`}
              >
                {hedged ? '~' : ''}
                {catalyst.eventName}
              </button>
            ) : null}
          </div>
          {whyItem == null && supportingDesks.length > 0 ? (
            <p className="truncate text-text-muted" title={supportingDesks.join(', ')}>
              <span className="text-text-secondary">Desks:</span> {supportingDesks.join(', ')}
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
        <Layers size={18} className="shrink-0 text-fin-blue" aria-hidden />
        <h2 className="text-base font-semibold text-text-primary md:text-lg">
          Confluence trade ideas
        </h2>
        {runDate ? (
          <span className="ml-auto font-mono text-[10px] text-text-muted">{runDate}</span>
        ) : null}
      </div>

      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 px-1">
        <p className="max-w-2xl text-xs text-text-muted">
          A directional cross-desk read meeting a near-term catalyst. Each idea&apos;s score blends
          consensus strength, event alignment and broker breadth — each shown as its own [0,1] leg.
        </p>
        <span className="font-mono text-[10px] text-text-muted">score 0–1 · higher = stronger</span>
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
        <div className="glass-card p-10 text-center text-sm text-text-muted">
          No confluence trade ideas{runDate ? ` for ${runDate}` : ''} yet.
        </div>
      )}
    </div>
  );
}
