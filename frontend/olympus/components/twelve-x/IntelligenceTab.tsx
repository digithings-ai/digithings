'use client';

import { useMemo } from 'react';
import Link from 'next/link';
import { usePathname, useSearchParams } from 'next/navigation';
import { Layers, Users, CalendarClock, FileText } from 'lucide-react';
import { briefHref } from './BriefPanel';
import type { FxConfluenceSnapshotRow } from '@/lib/twelve-x/types';

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
 * stacked-bar order. `recency`, `n_brokers`, `days_to_catalyst` are metadata,
 * surfaced as labels rather than bar segments.
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

/** Small horizontal stacked bar of the [0,1] score components (CSS, no recharts). */
function ComponentBar({ components }: { components: Record<string, number> }) {
  const segments = COMPONENT_SEGMENTS.map((s) => ({
    ...s,
    value: Math.max(0, components[s.key] ?? 0),
  }));
  const total = segments.reduce((sum, s) => sum + s.value, 0);
  if (total <= 0) return null;

  return (
    <div className="space-y-1.5">
      <div className="flex h-2 w-full overflow-hidden rounded-full bg-white/[0.05]">
        {segments.map((s) =>
          s.value > 0 ? (
            <div
              key={s.key}
              className="h-full first:rounded-l-full last:rounded-r-full"
              style={{ width: `${(s.value / total) * 100}%`, backgroundColor: s.color }}
              title={`${s.label}: ${s.value.toFixed(2)}`}
            />
          ) : null
        )}
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

function IntelligenceCard({ idea }: { idea: FxConfluenceSnapshotRow }) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const colorClass = directionColorClass(idea.direction);
  const components = useMemo(() => asComponents(idea.components), [idea.components]);
  const briefKeys = useMemo(() => asStringList(idea.brief_keys), [idea.brief_keys]);
  const nBrokers = asNumber(components.n_brokers);
  const daysToCatalyst = asNumber(components.days_to_catalyst);

  return (
    <div className="glass-card flex flex-col gap-3 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <span className="shrink-0 rounded border border-border-subtle bg-white/[0.06] px-1.5 py-0.5 font-mono text-[10px] text-text-muted">
            #{idea.rank}
          </span>
          <span className="truncate font-mono text-sm font-semibold text-text-primary">
            {idea.currency}
          </span>
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

      {(nBrokers != null || daysToCatalyst != null || briefKeys.length > 0) ? (
        <div className="mt-auto flex flex-wrap items-center gap-x-4 gap-y-1.5 border-t border-border-subtle/60 pt-2 text-[11px] text-text-muted">
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
              <span className="qn-metric tabular-nums text-text-secondary">{daysToCatalyst}</span>
              {daysToCatalyst === 1 ? 'day to catalyst' : 'days to catalyst'}
            </span>
          ) : null}
          {briefKeys.length > 0 ? (
            <Link
              href={briefHref(pathname, new URLSearchParams(searchParams.toString()), briefKeys[0])}
              scroll={false}
              className="ml-auto flex items-center gap-1 truncate text-fin-blue hover:underline"
              title={`Open brief ${briefKeys[0]}`}
            >
              <FileText size={12} aria-hidden />
              {briefKeys.length} source{briefKeys.length === 1 ? '' : 's'}
            </Link>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

export default function IntelligenceTab({
  confluence,
  runDate,
}: {
  confluence: FxConfluenceSnapshotRow[];
  runDate: string | null;
}) {
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

      <p className="max-w-2xl px-1 text-xs text-text-muted">
        A directional cross-desk read meeting a near-term catalyst. Each idea&apos;s score blends
        consensus strength, event alignment and broker breadth — shown as the stacked bar.
      </p>

      {confluence.length > 0 ? (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {confluence.map((idea) => (
            <IntelligenceCard key={`${idea.run_date}-${idea.rank}`} idea={idea} />
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
