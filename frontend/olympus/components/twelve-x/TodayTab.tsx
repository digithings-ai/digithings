'use client';

import { Sparkles, FileText, Users, Star } from 'lucide-react';
import { SafeMarkdown } from '@/components/SafeMarkdown';
import type { FxConfluenceSnapshotRow, Mover, ConsensusDeltaSet } from '@/lib/twelve-x/types';
import { useTwelveX } from './context';
import MoversStrip from './MoversStrip';

// TODO(defer): push alerts — no server in static export

interface DigestData {
  run_date: string;
  summary: string;
  key_themes: string[];
  doc_count: number;
  broker_count: number;
}

/** Map a confluence/consensus direction string to a .fin-* text color class. */
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

/** The base currency an idea files under (numerator of a pair, uppercased). */
function baseCurrency(currency: string): string {
  return currency.trim().toUpperCase().split('/')[0];
}

/**
 * `brief_keys` are broker NAMES per the data contract, not `source_file` keys.
 * Only treat an entry as a brief link target if it actually looks like a file
 * key (has a path separator or a file extension); otherwise we skip the link
 * rather than wire up a broken openBrief() call.
 */
function firstBriefSourceFile(briefKeys: unknown): string | null {
  if (!Array.isArray(briefKeys)) return null;
  for (const k of briefKeys) {
    if (typeof k !== 'string') continue;
    const s = k.trim();
    if (s && (s.includes('/') || /\.[a-z0-9]{2,5}$/i.test(s))) return s;
  }
  return null;
}

/**
 * Drop reciprocal legs of the same pair: if two ideas share the same instrument
 * with opposite (currency, direction) — e.g. "EUR/USD long" and "EUR/USD" filed
 * under USD short — keep only the higher-ranked one. Input is rank-sorted.
 */
function dedupeReciprocalLegs(ideas: FxConfluenceSnapshotRow[]): FxConfluenceSnapshotRow[] {
  const seenPairs = new Set<string>();
  const out: FxConfluenceSnapshotRow[] = [];
  const sorted = [...ideas].sort((a, b) => a.rank - b.rank);
  for (const idea of sorted) {
    const legs = idea.currency.trim().toUpperCase().split('/').filter(Boolean).sort();
    const pairKey = legs.join('|');
    if (pairKey && seenPairs.has(pairKey)) continue;
    if (pairKey) seenPairs.add(pairKey);
    out.push(idea);
  }
  return out;
}

function ConfluenceCard({ idea }: { idea: FxConfluenceSnapshotRow }) {
  const { crossLink, openBrief, watchlist } = useTwelveX();
  const colorClass = directionColorClass(idea.direction);
  const ccy = baseCurrency(idea.currency);
  const briefSource = firstBriefSourceFile(idea.brief_keys);
  const starred = watchlist.has(ccy);

  const cardInteractive = briefSource != null;
  const openCardBrief = () => {
    if (briefSource) openBrief(briefSource, idea.run_date);
  };

  return (
    <div
      className={`glass-card p-4 flex flex-col gap-2 transition-colors${
        cardInteractive
          ? ' cursor-pointer hover:border-fin-blue/50 focus-visible:border-fin-blue/50 focus-visible:outline-none'
          : ''
      }`}
      role={cardInteractive ? 'button' : undefined}
      tabIndex={cardInteractive ? 0 : undefined}
      onClick={cardInteractive ? openCardBrief : undefined}
      onKeyDown={
        cardInteractive
          ? (e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                openCardBrief();
              }
            }
          : undefined
      }
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-white/[0.06] text-text-muted border border-border-subtle shrink-0">
            #{idea.rank}
          </span>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              crossLink({ kind: 'currency', currency: ccy });
            }}
            className="font-mono text-sm font-semibold text-text-primary truncate hover:text-fin-blue transition-colors"
            title={`View ${ccy} consensus`}
          >
            {idea.currency}
          </button>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className={`text-xs font-semibold ${colorClass}`}>
            {directionLabel(idea.direction)}
          </span>
          <button
            type="button"
            aria-label={starred ? `Remove ${ccy} from watchlist` : `Add ${ccy} to watchlist`}
            aria-pressed={starred}
            onClick={(e) => {
              e.stopPropagation();
              watchlist.toggle(ccy);
            }}
            className={`transition-colors ${
              starred ? 'text-fin-amber' : 'text-text-muted hover:text-fin-amber'
            }`}
          >
            <Star size={14} fill={starred ? 'currentColor' : 'none'} aria-hidden />
          </button>
        </div>
      </div>
      <p className="text-sm text-text-primary leading-snug">{idea.title}</p>
      <div className="mt-auto flex items-center justify-between pt-1">
        <span className="text-[11px] text-text-muted uppercase tracking-wider">Score</span>
        <span className={`qn-metric tabular-nums ${colorClass}`}>
          {Number.isFinite(idea.score) ? idea.score.toFixed(2) : '—'}
        </span>
      </div>
    </div>
  );
}

export default function TodayTab({
  digest,
  confluence,
  runDate,
  movers,
  deltas,
}: {
  digest: DigestData | null;
  confluence: FxConfluenceSnapshotRow[];
  runDate: string | null;
  movers: Mover[];
  deltas: ConsensusDeltaSet;
}) {
  const { crossLink, watchlist } = useTwelveX();

  // De-dupe reciprocal legs (higher rank wins) before slicing the top ideas.
  const ranked = dedupeReciprocalLegs(confluence);
  const filtered = watchlist.filterOn
    ? ranked.filter((idea) => watchlist.has(baseCurrency(idea.currency)))
    : ranked;
  const topIdeas = filtered.slice(0, 6);

  const headerDate = runDate ?? digest?.run_date ?? null;

  return (
    <div className="space-y-4">
      {/* What changed — biggest consensus shifts since the previous run */}
      <MoversStrip
        movers={movers}
        onSelect={(currency) => crossLink({ kind: 'currency', currency })}
        title="What changed since last run"
      />

      {/* Header + top trade ideas */}
      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-3 px-1">
          <Sparkles size={16} className="text-fin-blue shrink-0" />
          <h2 className="text-base md:text-lg font-semibold text-text-primary">
            Top trade ideas
          </h2>
          {watchlist.items.length > 0 ? (
            <button
              type="button"
              onClick={() => watchlist.setFilterOn(!watchlist.filterOn)}
              aria-pressed={watchlist.filterOn}
              className={`text-[11px] font-medium px-2 py-0.5 rounded-full border transition-colors flex items-center gap-1 ${
                watchlist.filterOn
                  ? 'border-fin-amber/40 bg-fin-amber/10 text-fin-amber'
                  : 'border-border-subtle text-text-muted hover:text-text-secondary'
              }`}
            >
              <Star size={11} fill={watchlist.filterOn ? 'currentColor' : 'none'} aria-hidden />
              Watchlist
            </button>
          ) : null}
          <span className="text-[10px] font-mono text-text-muted ml-auto">{headerDate ?? '—'}</span>
        </div>

        {/* Score-scale legend */}
        <p className="text-[11px] text-text-muted px-1">
          Score 0–1 · higher = stronger confluence
        </p>

        {topIdeas.length > 0 ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {topIdeas.map((idea) => (
              <ConfluenceCard key={`${idea.run_date}-${idea.rank}`} idea={idea} />
            ))}
          </div>
        ) : (
          <div className="glass-card p-8 text-center text-text-muted text-sm">
            {watchlist.filterOn && ranked.length > 0
              ? 'No trade ideas match your watchlist.'
              : `No confluence trade ideas${headerDate ? ` for ${headerDate}` : ''}.`}
          </div>
        )}
      </div>

      {/* Full brief — demoted below the ideas, collapsed by default */}
      {digest ? (
        <details className="glass-card p-0 overflow-hidden group">
          <summary className="cursor-pointer list-none p-4 flex flex-wrap items-center gap-3 text-sm text-text-secondary hover:text-text-primary transition-colors">
            <FileText size={15} className="text-fin-blue shrink-0" aria-hidden />
            <span className="font-medium text-text-primary">Full brief</span>
            <span className="text-text-muted">
              · {digest.doc_count} {digest.doc_count === 1 ? 'doc' : 'docs'} ·{' '}
              {digest.broker_count} {digest.broker_count === 1 ? 'broker' : 'brokers'}
            </span>
            <span className="text-[10px] font-mono text-text-muted ml-auto">{digest.run_date}</span>
          </summary>

          <div className="px-4 pb-4 space-y-4 border-t border-border-subtle/60">
            {digest.summary ? (
              <SafeMarkdown className="prose prose-invert max-w-none text-sm text-text-secondary pt-4">
                {digest.summary}
              </SafeMarkdown>
            ) : null}

            {digest.key_themes.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {digest.key_themes.map((theme, i) => (
                  <span
                    key={`${theme}-${i}`}
                    className="text-[11px] font-medium px-2.5 py-1 rounded-full border border-fin-blue/30 bg-fin-blue/10 text-fin-blue"
                  >
                    {theme}
                  </span>
                ))}
              </div>
            ) : null}

            <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-xs text-text-muted">
              <span className="flex items-center gap-1.5">
                <FileText size={13} aria-hidden />
                <span className="qn-metric text-text-secondary tabular-nums">
                  {digest.doc_count}
                </span>
                documents
              </span>
              <span className="flex items-center gap-1.5">
                <Users size={13} aria-hidden />
                <span className="qn-metric text-text-secondary tabular-nums">
                  {digest.broker_count}
                </span>
                brokers
              </span>
            </div>
          </div>
        </details>
      ) : null}
    </div>
  );
}
