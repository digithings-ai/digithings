'use client';

import { useMemo, useState } from 'react';
import { ChevronRight, Grid3x3 } from 'lucide-react';

import { G10_CURRENCIES } from '@/lib/twelve-x/types';
import type { MatrixCell } from '@/lib/twelve-x/types';

const SCORE_MAX = 2;
const LEAN_BAND = 0.35;
const STRONG_BAND = 1.25;

type Bucket = 'bull' | 'bear' | 'watch' | 'neutral';

/** Map a currency-view direction onto a coarse bucket. */
function directionBucket(direction: string): Bucket {
  const d = direction.trim().toLowerCase();
  if (d === 'bullish' || d === 'long' || d === 'buy') return 'bull';
  if (d === 'bearish' || d === 'short' || d === 'sell') return 'bear';
  if (d === 'watch') return 'watch';
  return 'neutral';
}

/** Bucket → glyph + .fin-* text color for the per-desk rows. */
function bucketStyle(bucket: Bucket): { text: string; glyph: string } {
  if (bucket === 'bull') return { text: 'text-fin-green', glyph: '▲' };
  if (bucket === 'bear') return { text: 'text-fin-red', glyph: '▼' };
  if (bucket === 'watch') return { text: 'text-fin-amber', glyph: '◆' };
  return { text: 'text-text-secondary', glyph: '•' };
}

/** Conviction → weight (matches the twelve-x consensus weighting). */
function convictionWeight(conviction: string): number {
  const c = conviction.trim().toLowerCase();
  if (c === 'high') return 1;
  if (c === 'medium' || c === 'mid') return 0.65;
  if (c === 'low') return 0.35;
  return 0.65;
}

function convictionLabel(conviction: string): string {
  const c = conviction.trim();
  if (!c) return '';
  return c.charAt(0).toUpperCase() + c.slice(1).toLowerCase();
}

/** Plain-English net read — same bands as ConsensusTab so the suite stays consistent. */
function scoreLabel(score: number): string {
  if (score >= STRONG_BAND) return 'Strong bull';
  if (score >= LEAN_BAND) return 'Bullish lean';
  if (score <= -STRONG_BAND) return 'Strong bear';
  if (score <= -LEAN_BAND) return 'Bearish lean';
  return 'Neutral';
}

function scoreColorClass(score: number): string {
  if (score >= LEAN_BAND) return 'text-fin-green';
  if (score <= -LEAN_BAND) return 'text-fin-red';
  return 'text-text-secondary';
}

interface CurrencyAgg {
  currency: string;
  cells: MatrixCell[];
  bull: number;
  bear: number;
  watch: number;
  neutral: number;
  nDesks: number;
  score: number;
  thin: boolean;
}

/** Aggregate one currency's desk cells into a net lean + a split, porting the
 * consensus score shape (tilt × (1 + agreement)) so the Matrix net lean doesn't
 * visibly disagree with the Consensus tab. */
function aggregate(currency: string, cells: MatrixCell[]): CurrencyAgg {
  let bull = 0;
  let bear = 0;
  let watch = 0;
  let neutral = 0;
  let tiltSum = 0;
  for (const c of cells) {
    const b = directionBucket(c.direction);
    if (b === 'bull') bull++;
    else if (b === 'bear') bear++;
    else if (b === 'watch') watch++;
    else neutral++;
    const dir = b === 'bull' ? 1 : b === 'bear' ? -1 : 0;
    tiltSum += dir * convictionWeight(c.conviction);
  }
  const n = cells.length;
  const tilt = n > 0 ? tiltSum / n : 0;
  const directional = bull + bear;
  const agreement = directional > 0 ? Math.min(1, Math.max(0, (Math.max(bull, bear) / directional - 0.5) / 0.5)) : 0;
  const score = Math.min(SCORE_MAX, Math.max(-SCORE_MAX, tilt * (1 + agreement)));
  const nDesks = new Set(cells.map((c) => c.broker)).size;
  return { currency, cells, bull, bear, watch, neutral, nDesks, score, thin: nDesks < 2 };
}

/** Order the per-desk rows within an expanded currency: bull, bear, then watch/neutral. */
const BUCKET_ORDER: Bucket[] = ['bull', 'bear', 'watch', 'neutral'];

function DeskRow({
  cell,
  onOpenBrief,
}: {
  cell: MatrixCell;
  onOpenBrief: (sourceFile: string, runDate: string | null) => void;
}) {
  const bucket = directionBucket(cell.direction);
  const s = bucketStyle(bucket);
  const date = cell.report_date || cell.run_date;
  return (
    <button
      type="button"
      onClick={() => onOpenBrief(cell.source_file, cell.run_date)}
      className="flex w-full items-center gap-3 rounded-md px-3 py-2 text-left transition-colors hover:bg-white/[0.04]"
      title={`${cell.broker} · ${cell.direction}${cell.conviction ? ` (${cell.conviction})` : ''}${
        cell.signal ? ` — ${cell.signal}` : ''
      } · ${date} — open brief`}
    >
      <span className={`w-3 shrink-0 text-center text-sm leading-none ${s.text}`} aria-hidden>
        {s.glyph}
      </span>
      <span className="w-40 shrink-0 truncate text-sm font-medium text-text-primary">{cell.broker}</span>
      {cell.conviction ? (
        <span className="shrink-0 rounded border border-border-subtle bg-white/[0.04] px-1.5 py-0.5 text-[9px] uppercase tracking-wide text-text-muted">
          {convictionLabel(cell.conviction)}
        </span>
      ) : null}
      <span className="min-w-0 flex-1 truncate text-xs text-text-secondary">{cell.signal || ''}</span>
      <span className="shrink-0 font-mono text-[10px] text-text-muted/70">{date?.slice(5) ?? ''}</span>
    </button>
  );
}

function CurrencyAccordion({
  agg,
  open,
  onToggle,
  onOpenBrief,
}: {
  agg: CurrencyAgg;
  open: boolean;
  onToggle: () => void;
  onOpenBrief: (sourceFile: string, runDate: string | null) => void;
}) {
  const frac = Math.min(1, Math.abs(agg.score) / SCORE_MAX);
  const bullish = agg.score >= 0;
  const colorClass = scoreColorClass(agg.score);

  return (
    <div className={agg.thin ? 'opacity-60' : ''}>
      <button
        type="button"
        onClick={onToggle}
        className="grid w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-white/[0.02]"
        style={{ gridTemplateColumns: 'minmax(56px,64px) minmax(120px,1fr) 96px minmax(120px,180px) 64px 20px' }}
        aria-expanded={open}
      >
        {/* Currency */}
        <span className="font-mono text-sm font-semibold text-text-primary">{agg.currency}</span>

        {/* Net-lean bar (centered zero, fills right=bull / left=bear) */}
        <div className="flex items-center gap-2">
          <div className="relative h-2 flex-1 overflow-hidden rounded-full bg-white/[0.05]">
            <div className="absolute inset-y-0 left-1/2 w-px bg-white/20" />
            <div
              className={`absolute inset-y-0 ${bullish ? 'left-1/2' : 'right-1/2'} ${
                bullish ? 'bg-fin-green' : 'bg-fin-red'
              }`}
              style={{ width: `${frac * 50}%` }}
            />
          </div>
          <span className={`qn-metric w-10 shrink-0 text-right tabular-nums ${colorClass}`}>
            {agg.score.toFixed(2)}
          </span>
        </div>

        {/* Plain-English label */}
        <span className={`text-xs font-medium ${colorClass}`}>{scoreLabel(agg.score)}</span>

        {/* Split chip — desk counts by direction */}
        <span className="flex items-center gap-2 text-[11px] tabular-nums">
          <span className="text-fin-green">▲{agg.bull}</span>
          <span className="text-fin-red">▼{agg.bear}</span>
          {agg.watch > 0 ? <span className="text-fin-amber">◆{agg.watch}</span> : null}
          {agg.neutral > 0 ? <span className="text-text-muted">•{agg.neutral}</span> : null}
        </span>

        {/* Coverage */}
        <span className="text-right text-[11px] text-text-muted">
          {agg.nDesks} desk{agg.nDesks === 1 ? '' : 's'}
          {agg.thin ? <span className="ml-1 text-text-muted/60">· thin</span> : null}
        </span>

        <ChevronRight
          size={14}
          aria-hidden
          className={`text-text-muted transition-transform ${open ? 'rotate-90' : ''}`}
        />
      </button>

      {open ? (
        <div className="space-y-3 border-t border-border-subtle/60 bg-white/[0.01] px-3 py-3">
          {BUCKET_ORDER.map((bucket) => {
            const inBucket = agg.cells
              .filter((c) => directionBucket(c.direction) === bucket)
              .sort((a, b) => a.broker.localeCompare(b.broker));
            if (inBucket.length === 0) return null;
            const heading =
              bucket === 'bull' ? 'Bull' : bucket === 'bear' ? 'Bear' : bucket === 'watch' ? 'Watch' : 'Neutral';
            const headColor = bucketStyle(bucket).text;
            return (
              <div key={bucket}>
                <p className={`px-3 pb-1 text-[10px] font-semibold uppercase tracking-wider ${headColor}`}>
                  {heading} · {inBucket.length}
                </p>
                <div className="space-y-0.5">
                  {inBucket.map((cell) => (
                    <DeskRow key={`${cell.broker}-${cell.run_date}`} cell={cell} onOpenBrief={onOpenBrief} />
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}

export default function MatrixTab({
  cells,
  onOpenBrief,
}: {
  cells: MatrixCell[];
  onOpenBrief: (sourceFile: string, runDate: string | null) => void;
}) {
  // One aggregate per currency the desks actually cover, ordered by conviction
  // strength (largest absolute net lean first) so the strongest reads sit on top.
  const perCurrency = useMemo<CurrencyAgg[]>(() => {
    const byCcy = new Map<string, MatrixCell[]>();
    for (const c of cells) {
      const list = byCcy.get(c.currency) ?? [];
      list.push(c);
      byCcy.set(c.currency, list);
    }
    const order = (ccy: string) => {
      const i = (G10_CURRENCIES as readonly string[]).indexOf(ccy);
      return i === -1 ? G10_CURRENCIES.length : i;
    };
    return [...byCcy.entries()]
      .map(([ccy, list]) => aggregate(ccy, list))
      .sort((a, b) => {
        const d = Math.abs(b.score) - Math.abs(a.score);
        if (Math.abs(d) > 1e-9) return d;
        return order(a.currency) - order(b.currency);
      });
  }, [cells]);

  const [openCcy, setOpenCcy] = useState<string | null>(null);
  const hasData = perCurrency.length > 0;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3 px-1">
        <Grid3x3 size={18} className="shrink-0 text-fin-blue" aria-hidden />
        <h2 className="text-base font-semibold text-text-primary md:text-lg">Desk view by currency</h2>
      </div>

      <p className="max-w-2xl px-1 text-xs text-text-muted">
        The street&apos;s net read per G10 currency over a recent window — scannable at a glance, ranked
        by conviction. Expand a currency to see the desks behind it (bull / bear / watch) and click any
        desk to open its brief.
      </p>

      {hasData ? (
        <div className="glass-card overflow-hidden p-0">
          <div className="divide-y divide-border-subtle">
            {perCurrency.map((agg) => (
              <CurrencyAccordion
                key={agg.currency}
                agg={agg}
                open={openCcy === agg.currency}
                onToggle={() => setOpenCcy((cur) => (cur === agg.currency ? null : agg.currency))}
                onOpenBrief={onOpenBrief}
              />
            ))}
          </div>

          {/* Legend */}
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 border-t border-border-subtle bg-bg-secondary px-4 py-2.5 text-[11px] text-text-muted">
            <span className="flex items-center gap-1.5">
              <span className="text-fin-green" aria-hidden>▲</span> Bull
            </span>
            <span className="flex items-center gap-1.5">
              <span className="text-fin-red" aria-hidden>▼</span> Bear
            </span>
            <span className="flex items-center gap-1.5">
              <span className="text-fin-amber" aria-hidden>◆</span> Watch
            </span>
            <span className="flex items-center gap-1.5">
              <span className="text-text-secondary" aria-hidden>•</span> Neutral
            </span>
            <span className="ml-auto">Bar = net lean · click a currency to expand its desks</span>
          </div>
        </div>
      ) : (
        <div className="glass-card p-10 text-center text-sm text-text-muted">
          No desk views available in the recent window.
        </div>
      )}
    </div>
  );
}
