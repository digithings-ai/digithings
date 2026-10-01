'use client';

import { useMemo, useState } from 'react';
import { Badge, Button, Card, RangeTrack } from '@digithings/ui/ui';
import type { FxTradeIdeaRow } from '@/lib/twelve-x/types';
import {
  continuityForBoard,
  continuityKey,
  formatBoardDate,
  formatContinuityLine,
  formatPublishAsOf,
  type IdeaContinuityMeta,
} from '@/lib/twelve-x/idea-continuity';
import { buildIdeaLadder } from '@/lib/twelve-x/idea-ladder';
import { buildIdeaDetailModel, type IdeaDetailLevelRow } from '@/lib/twelve-x/trade-levels';
import { useTwelveX } from './context';
import { TwelveXSectionHeading } from './TwelveXSectionHeading';
import LevelFixSection from './LevelFixSection';

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
    <Badge
      variant="outline"
      className="border-hair bg-surface/50 px-1 font-mono text-[10px] text-ink-mute"
    >
      {label}
    </Badge>
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
          ? 'flex flex-wrap items-center gap-x-2 gap-y-0.5 rounded-none border border-hair bg-surface/40 px-1.5 py-1 text-[11px]'
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
  const [openEvidence, setOpenEvidence] = useState<number[]>([]);
  const toggleEvidenceDetail = (index: number) =>
    setOpenEvidence((open) =>
      open.includes(index) ? open.filter((i) => i !== index) : [...open, index],
    );
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
              {evidenceRows.map((row, index) => (
                <div
                  key={`${index}-${row.instrument}-${row.statement}`}
                  className="space-y-0.5 text-[11px]"
                >
                  <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                    <ProvenanceChip label={`${row.sourceLabel} · ${row.instrument}`} />
                    <span className={row.className}>{row.summary}</span>
                    <span className="font-mono text-[10px] text-ink-mute">{row.stance}</span>
                    {row.detail ? (
                      <Button
                        type="button"
                        variant="link"
                        size="xs"
                        className="h-auto p-0 font-mono text-[10px] text-ink-mute underline decoration-dotted hover:text-accent"
                        onClick={(event) => {
                          event.stopPropagation();
                          toggleEvidenceDetail(index);
                        }}
                        aria-expanded={openEvidence.includes(index)}
                      >
                        {openEvidence.includes(index) ? 'hide detail' : 'detail'}
                      </Button>
                    ) : null}
                  </div>
                  {row.detail && openEvidence.includes(index) ? (
                    <p className="font-mono text-[10px] leading-relaxed text-ink-mute">
                      {row.detail}
                    </p>
                  ) : null}
                </div>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
      {showLevels ? (
        <div className="pt-1">
          <LevelFixSection idea={idea} />
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

/** Direction glyph + word; bullish/long reads accent, bearish/short warn (never P&L up/down). */
function directionGlyph(direction: string): string {
  const d = direction.toLowerCase();
  if (d.includes('long') || d.includes('bull')) return '▲';
  if (d.includes('short') || d.includes('bear')) return '▼';
  return '•';
}

/**
 * Today's ranked trade ideas as a ladder: one row per idea with its level
 * range drawn as a RangeTrack (stop / entry / target positions on one axis).
 * Every row is a button that opens the idea slide-over; disputed ideas get a
 * warn ring when the dispute toggle is on.
 */
export default function TradeIdeasPanel({
  ideas,
  highlightRanks,
  ideaHistory = [],
}: {
  ideas: FxTradeIdeaRow[];
  highlightRanks?: ReadonlySet<number>;
  ideaHistory?: Pick<FxTradeIdeaRow, 'run_date' | 'pair' | 'direction' | 'as_of'>[];
}) {
  const { crossLink, openIdea } = useTwelveX();

  const boardDate = ideas[0]?.run_date ?? '';
  const continuity = useMemo(() => {
    const fromIdeas = ideas.map((i) => ({
      run_date: i.run_date,
      pair: i.pair,
      direction: i.direction,
      as_of: i.as_of,
    }));
    let hist = ideaHistory.length > 0 ? [...ideaHistory] : fromIdeas;
    // Prefer including the displayed board: if history omits boardDate, merge ideas in.
    if (boardDate && ideas.length > 0 && !hist.some((h) => h.run_date === boardDate)) {
      hist = [...hist, ...fromIdeas];
    }
    let map = continuityForBoard(boardDate, hist);
    // Harden: empty continuity with live ideas → merge board rows and recompute.
    if (map.size === 0 && ideas.length > 0 && boardDate) {
      map = continuityForBoard(boardDate, [...hist, ...fromIdeas]);
    }
    return map;
  }, [boardDate, ideaHistory, ideas]);

  const metaFor = (idea: FxTradeIdeaRow) => continuity.get(continuityKey(idea.pair, idea.direction));

  const ladders = useMemo(() => ideas.map((i) => buildIdeaLadder(i)), [ideas]);

  return (
    <Card data-reveal className="flex flex-col gap-3 p-4">
      <header className="flex items-baseline gap-2">
        <TwelveXSectionHeading>Today&rsquo;s trade ideas</TwelveXSectionHeading>
        <span className="font-mono text-[10px] text-ink-mute">· {ideas.length}</span>
        <Button
          type="button"
          variant="link"
          size="xs"
          className="ml-auto h-auto p-0 text-[11px] text-accent"
          onClick={() => crossLink({ kind: 'ideas' })}
        >
          see more →
        </Button>
      </header>

      {ideas.length === 0 ? (
        <p className="text-sm text-ink-mute">No curated trade idea for today yet.</p>
      ) : (
        <ul className="flex flex-col gap-2" aria-label="Ranked trade ideas">
          {ideas.map((idea, index) => {
            const ladder = ladders[index];
            const disputed = highlightRanks?.has(idea.rank) ?? false;
            return (
              <li key={`${idea.run_date}-${idea.rank}`}>
                <Button
                  type="button"
                  variant="ghost"
                  data-idea-rank={idea.rank}
                  data-disputed={disputed ? 'true' : undefined}
                  className={`block h-auto w-full justify-start whitespace-normal rounded-none border px-3 py-2 text-left text-xs font-normal transition-colors hover:border-accent/50 hover:bg-transparent ${
                    disputed
                      ? 'border-warn/60 ring-2 ring-warn/40 ring-offset-1 ring-offset-surface'
                      : index === 0
                        ? 'border-accent/30 bg-accent/[0.06]'
                        : 'border-hair'
                  }`}
                  onClick={() => openIdea(idea.run_date, idea.rank)}
                >
                  <span className="flex min-w-0 items-start gap-2">
                    <span className="flex min-w-0 flex-1 flex-wrap items-center gap-x-2 gap-y-0.5">
                      <span className="font-mono text-[10px] text-ink-mute">#{idea.rank}</span>
                      <span className="font-semibold text-ink">{idea.pair}</span>
                      <span className={`font-semibold uppercase ${dirClass(idea.direction)}`}>
                        <span aria-hidden>{directionGlyph(idea.direction)} </span>
                        {idea.direction}
                      </span>
                      <span className="min-w-0 flex-1 truncate text-ink-mute">{idea.title}</span>
                    </span>
                    <ContinuityStamp meta={metaFor(idea)} />
                  </span>
                  {ladder ? (
                    <RangeTrack
                      className="mt-1.5"
                      low={ladder.low}
                      high={ladder.high}
                      label={`${idea.pair} ${idea.direction} level range`}
                      markers={ladder.markers.map((m) => ({
                        kind: m.kind,
                        value: m.value,
                        label: m.label,
                      }))}
                      format={(v) => String(Math.round(v * 1e5) / 1e5)}
                    />
                  ) : null}
                </Button>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}
