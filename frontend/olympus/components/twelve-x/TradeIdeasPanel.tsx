'use client';

import { useMemo, useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import type { FxTradeIdeaRow, FxConfluenceSnapshotRow } from '@/lib/twelve-x/types';
import {
  continuityForBoard,
  continuityKey,
  formatBoardDate,
  formatContinuityLine,
  formatPublishAsOf,
  type IdeaContinuityMeta,
} from '@/lib/twelve-x/idea-continuity';
import { buildIdeaDetailModel, type IdeaDetailLevelRow } from '@/lib/twelve-x/trade-levels';
import { useTwelveX } from './context';
import { TwelveXSectionHeading } from './TwelveXSectionHeading';

function dirClass(direction: string): string {
  const d = direction.toLowerCase();
  if (d.includes('long') || d.includes('bull')) return 'text-accent';
  if (d.includes('short') || d.includes('bear')) return 'text-warn';
  return 'text-ink-mute';
}

/**
 * Human label for a citation object. Trade ideas are run artifacts — their
 * citations name contributing desks but do NOT resolve to loadable briefs, so
 * the panel expands detail in place instead of opening the brief slide-over.
 */
function citationLabel(c: unknown): string | null {
  if (!c || typeof c !== 'object') return null;
  const rec = c as Record<string, unknown>;
  for (const key of ['broker', 'broker_name', 'desk', 'source']) {
    if (typeof rec[key] === 'string' && (rec[key] as string).trim()) return rec[key] as string;
  }
  if (typeof rec.source_file === 'string' && rec.source_file.trim()) {
    const stem = rec.source_file.split('/').pop() ?? rec.source_file;
    return stem.replace(/\.(md|json|pdf)$/i, '').replace(/[-_]+/g, ' ');
  }
  return null;
}

function contributingDesks(citations: unknown[]): string[] {
  return [...new Set(citations.map(citationLabel).filter((v): v is string => !!v))];
}

function ProvenanceChip({ label }: { label: string }) {
  return (
    <span className="rounded border border-hair bg-surface/50 px-1 font-mono text-[10px] text-ink-mute">
      {label}
    </span>
  );
}

function levelValueClass(role: IdeaDetailLevelRow['role']): string {
  switch (role) {
    case 'target':
      return 'font-mono tabular-nums text-accent';
    case 'stop':
      return 'font-mono tabular-nums text-warn';
    case 'entry':
      return 'font-mono tabular-nums text-ink';
    default: {
      const _exhaustive: never = role;
      return _exhaustive;
    }
  }
}

function LadderRow({ row }: { row: IdeaDetailLevelRow }) {
  const boxed = row.role === 'entry';
  return (
    <div
      className={
        boxed
          ? 'flex flex-wrap items-center gap-x-2 gap-y-0.5 rounded border border-hair bg-surface/40 px-1.5 py-1 text-[11px]'
          : 'flex flex-wrap items-center gap-x-2 gap-y-0.5 px-1.5 text-[11px]'
      }
    >
      <span className="w-12 shrink-0 text-ink-mute">{row.label}</span>
      <span className={levelValueClass(row.role)}>{row.value}</span>
      <ProvenanceChip label={row.chip} />
    </div>
  );
}

/** Dual column only when both levels and evidence exist — never an empty placeholder col. */
export function ideaDetailBlocksClass(hasLevels: boolean, hasEvidence: boolean): string {
  return hasLevels && hasEvidence
    ? 'grid grid-cols-1 gap-3 sm:grid-cols-2'
    : 'grid grid-cols-1 gap-3';
}

export function IdeaDetail({ idea }: { idea: FxTradeIdeaRow }) {
  const { status, riskRewardLabel, levelRows, evidenceRows } = buildIdeaDetailModel(idea);
  const desks = contributingDesks(idea.citations);
  const showLevels = levelRows.length > 0;
  const showEvidence = evidenceRows.length > 0;
  const showGrid = showLevels || showEvidence;

  return (
    <div className="mt-2 space-y-2 border-t border-hair pt-2 text-left">
      {idea.thesis ? <p className="text-xs leading-relaxed text-ink-soft">{idea.thesis}</p> : null}
      {idea.catalyst ? (
        <p className="text-[11px] text-ink-mute">Catalyst: {idea.catalyst}</p>
      ) : null}
      {showGrid ? (
        <div className={ideaDetailBlocksClass(showLevels, showEvidence)}>
          {showLevels ? (
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <span className="text-[11px] text-ink-soft">Levels</span>
                {status && status !== 'complete' ? (
                  <span className="font-mono text-[10px] text-ink-mute">{status}</span>
                ) : null}
              </div>
              <div className="space-y-0.5">
                {levelRows.map((row) => (
                  <LadderRow key={`${row.role}-${row.label}-${row.value}`} row={row} />
                ))}
              </div>
              {riskRewardLabel != null ? (
                <p className="font-mono text-[10px] text-ink-mute">R:R {riskRewardLabel}</p>
              ) : null}
            </div>
          ) : null}
          {showEvidence ? (
            <div className="space-y-1">
              <p className="text-[11px] text-ink-soft">Market evidence</p>
              {evidenceRows.map((row) => (
                <div
                  key={row.statement}
                  className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 text-[11px]"
                >
                  <span className={row.className}>{row.statement}</span>
                  <span className="font-mono text-[10px] text-ink-mute">{row.stance}</span>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
      {desks.length > 0 ? (
        <p className="text-[11px] text-ink-mute">
          Contributing desks: <span className="text-ink-soft">{desks.join(' · ')}</span>
        </p>
      ) : null}
    </div>
  );
}

/** Card-header stamp: stack Suggested / Updated so narrow cards wrap cleanly. */
function ContinuityStamp({ meta }: { meta: IdeaContinuityMeta | undefined }) {
  if (!meta) return null;
  const suggestedLabel = meta.boardsOnThread <= 1 ? 'Suggested' : 'First suggested';
  const suggested = `${suggestedLabel} ${formatBoardDate(meta.firstSuggested)}`;
  const updated = `Updated ${formatPublishAsOf(meta.lastUpdated)}`;
  return (
    <span
      className="ml-auto min-w-0 max-w-[min(100%,14rem)] text-right font-mono text-[10px] leading-snug text-ink-mute"
      title={formatContinuityLine(meta)}
    >
      <span className="block break-words">{suggested}</span>
      <span className="block break-words">{updated}</span>
    </span>
  );
}

export default function TradeIdeasPanel({
  ideas,
  confluence,
  highlightRanks,
  ideaHistory = [],
}: {
  ideas: FxTradeIdeaRow[];
  confluence: FxConfluenceSnapshotRow[];
  highlightRanks?: ReadonlySet<number>;
  ideaHistory?: Pick<FxTradeIdeaRow, 'run_date' | 'pair' | 'direction' | 'as_of'>[];
}) {
  const { crossLink } = useTwelveX();
  const [expanded, setExpanded] = useState(false);
  const [openRank, setOpenRank] = useState<number | null>(null);
  const toggleIdea = (rank: number) => setOpenRank((v) => (v === rank ? null : rank));

  const boardDate = ideas[0]?.run_date ?? '';
  const continuity = useMemo(() => {
    const fromIdeas = ideas.map((i) => ({
      run_date: i.run_date,
      pair: i.pair,
      direction: i.direction,
      as_of: i.as_of,
    }));
    let hist =
      ideaHistory.length > 0 ? [...ideaHistory] : fromIdeas;
    // Prefer including the displayed board: if history omits boardDate, merge ideas in.
    if (
      boardDate &&
      ideas.length > 0 &&
      !hist.some((h) => h.run_date === boardDate)
    ) {
      hist = [...hist, ...fromIdeas];
    }
    let map = continuityForBoard(boardDate, hist);
    // Harden: empty continuity with live ideas → merge board rows and recompute.
    if (map.size === 0 && ideas.length > 0 && boardDate) {
      map = continuityForBoard(boardDate, [...hist, ...fromIdeas]);
    }
    return map;
  }, [boardDate, ideaHistory, ideas]);

  const metaFor = (idea: FxTradeIdeaRow) =>
    continuity.get(continuityKey(idea.pair, idea.direction));

  const highlightClass = (rank: number, base: string) =>
    highlightRanks?.has(rank)
      ? `${base} ring-2 ring-warn/50 ring-offset-1 ring-offset-surface`
      : base;

  if (ideas.length === 0) {
    return (
      <section className="glass-card p-5">
        <header className="mb-2 flex items-baseline gap-2">
          <TwelveXSectionHeading>Today&rsquo;s trade ideas</TwelveXSectionHeading>
        </header>
        <p className="text-sm text-ink-mute">No curated trade idea for today yet.</p>
      </section>
    );
  }

  const [top, ...rest] = ideas;

  return (
    <section className="glass-card flex flex-col gap-3 p-5">
      <header className="flex items-baseline gap-2">
        <TwelveXSectionHeading>Today&rsquo;s trade ideas</TwelveXSectionHeading>
        <span className="font-mono text-[10px] text-ink-mute">· {ideas.length}</span>
        <button
          type="button"
          className="ml-auto text-[11px] text-accent hover:underline"
          onClick={() => crossLink({ kind: 'tab', tab: 'consensus' })}
        >
          see more →
        </button>
      </header>

      {/* Focal #1 — accent chrome marks it as the top-ranked idea, NOT a P&L
          direction. --up/--down are reserved for P&L sign (F5), so a SHORT #1
          must not read as green. Direction lives in its own colored label. */}
      <button
        type="button"
        className={highlightClass(
          top.rank,
          'rounded-lg border border-accent/30 bg-accent/[0.06] p-4 text-left transition-colors hover:border-accent/50',
        )}
        onClick={() => toggleIdea(top.rank)}
        aria-expanded={openRank === top.rank}
      >
        <div className="flex min-w-0 items-start gap-2">
          <div className="flex min-w-0 flex-1 flex-wrap items-center gap-x-2 gap-y-0.5">
            <span className="font-mono text-[11px] text-ink-mute">#1</span>
            <span className="font-semibold text-ink">{top.pair}</span>
            <span className={`text-xs font-semibold uppercase ${dirClass(top.direction)}`}>
              {top.direction}
            </span>
          </div>
          <ContinuityStamp meta={metaFor(top)} />
        </div>
        <p className="mt-1 text-sm text-ink">{top.title}</p>
        {openRank === top.rank ? (
          <IdeaDetail idea={top} />
        ) : (
          <>
            {top.thesis ? <p className="mt-1 line-clamp-2 text-xs text-ink-soft">{top.thesis}</p> : null}
            {top.catalyst ? <p className="mt-1 text-[11px] text-ink-mute">Catalyst: {top.catalyst}</p> : null}
          </>
        )}
      </button>

      {/* #2…N rows — expand in place; ideas are run artifacts with no brief */}
      {rest.map((idea) => (
        <button
          key={`${idea.run_date}-${idea.rank}`}
          type="button"
          className={highlightClass(
            idea.rank,
            'rounded-md border border-hair px-3 py-2 text-left text-xs transition-colors hover:border-accent/50',
          )}
          onClick={() => toggleIdea(idea.rank)}
          aria-expanded={openRank === idea.rank}
        >
          <span className="flex min-w-0 items-start gap-2">
            <span className="flex min-w-0 flex-1 flex-wrap items-center gap-x-2 gap-y-0.5">
              <span className="font-mono text-[10px] text-ink-mute">#{idea.rank}</span>
              <span className="font-semibold text-ink">{idea.pair}</span>
              <span className={`font-semibold uppercase ${dirClass(idea.direction)}`}>
                {idea.direction}
              </span>
              <span className="min-w-0 flex-1 truncate text-ink-mute">{idea.title}</span>
            </span>
            <ContinuityStamp meta={metaFor(idea)} />
          </span>
          {openRank === idea.rank ? <IdeaDetail idea={idea} /> : null}
        </button>
      ))}

      {/* Expand → confluence reads */}
      {confluence.length > 0 ? (
        <div>
          <button
            type="button"
            className="flex items-center gap-1 text-[11px] text-ink-soft hover:text-accent"
            onClick={() => setExpanded((v) => !v)}
            aria-expanded={expanded}
          >
            {expanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
            {expanded ? 'Hide' : 'Expand'} confluence reads ({confluence.length})
          </button>
          {expanded ? (
            <ul className="mt-2 grid gap-1">
              {confluence.map((c) => (
                <li
                  key={`${c.run_date}-${c.rank}`}
                  className="flex items-center gap-2 rounded-md border border-hair px-3 py-1.5 text-xs"
                >
                  <span className="font-mono text-[10px] text-ink-mute">#{c.rank}</span>
                  <span className="font-semibold text-ink">{c.currency}</span>
                  <span className={`uppercase ${dirClass(c.direction)}`}>{c.direction}</span>
                  <button
                    type="button"
                    className="ml-auto text-accent hover:underline"
                    onClick={() => crossLink({ kind: 'currency', currency: c.currency })}
                  >
                    trend →
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
