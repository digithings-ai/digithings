'use client';

import { useMemo, useState } from 'react';
import { FileText, Target } from 'lucide-react';
import { Sheet, SheetContent, SheetTitle } from '@digithings/web';
import { Button } from '@digithings/web/ui';

import DetailPanelHeaderActions, {
  detailPanelSheetSizeClass,
  type DetailPanelSize,
} from '@/components/DetailPanelHeaderActions';
import {
  assembleTradeHistory,
  biasLabel,
  closeReason,
  finalResult,
  formatHoldPct,
  tradeResult,
  type TradeHistoryRow,
} from '@/lib/twelve-x/trade-history';
import type { FxIdeaEvalRow, FxTradeIdeaRow } from '@/lib/twelve-x/types';
import { useTwelveX } from './context';
import { IdeaDetail } from './TradeIdeasPanel';

interface Citation {
  broker?: string;
  source_file?: string;
}

function parseCitations(raw: unknown): Citation[] {
  if (!Array.isArray(raw)) return [];
  return raw.flatMap((item): Citation[] => {
    if (typeof item !== 'object' || item === null) return [];
    const rec = item as Record<string, unknown>;
    const sourceFile = typeof rec.source_file === 'string' ? rec.source_file : undefined;
    const broker = typeof rec.broker === 'string' ? rec.broker : undefined;
    if (!sourceFile && !broker) return [];
    return [{ source_file: sourceFile, broker }];
  });
}

const RESULT_LABELS: Record<string, string> = {
  right: 'Right',
  wrong: 'Wrong',
  live: 'Live',
  closed: 'Closed',
};

function LifecycleStat({ label, value, title }: { label: string; value: string; title?: string }) {
  return (
    <div className="flex flex-col gap-0.5" title={title}>
      <span className="text-[10px] font-semibold uppercase tracking-wider text-ink-mute">
        {label}
      </span>
      <span className="font-mono text-xs text-ink">{value}</span>
    </div>
  );
}

/**
 * The full lifecycle story for one trade idea: how it ended (Status), whether
 * it graded Right / Wrong (measured at the level when it filled, directional
 * when it never filled), the final impact, and the bookkeeper's reasoning.
 * Split from the panel chrome so the static-SSR tests can target it directly.
 */
export function IdeaLifecycleBlock({ row }: { row: TradeHistoryRow }) {
  const close = closeReason(row);
  const result = tradeResult(row);
  const final = finalResult(row);

  return (
    <section
      className="rounded-none border border-hair bg-ink/[0.02] p-3"
      aria-label="Trade lifecycle"
    >
      <h3 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-ink-mute">
        Lifecycle
      </h3>

      <div className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-4">
        <LifecycleStat label="Status" value={close.label} title={close.detail} />
        <LifecycleStat
          label="Result"
          value={result === null ? '—' : (RESULT_LABELS[result] ?? result)}
        />
        <LifecycleStat
          label="Final impact"
          value={final === null ? '—' : formatHoldPct(final.pct)}
          title={
            final === null
              ? undefined
              : final.basis === 'measured'
                ? 'Measured at the filled bracket / exit close'
                : final.basis === 'directional'
                  ? 'Directional grade — entry never filled'
                  : undefined
          }
        />
        <LifecycleStat label="Sessions" value={row.sessions === null ? '—' : String(row.sessions)} />
      </div>

      <dl className="mt-3 space-y-1.5 text-xs">
        <div className="flex gap-2">
          <dt className="w-24 shrink-0 text-ink-mute">Entry</dt>
          <dd className="font-mono text-ink-soft">
            {row.entryDate ?? '—'}
            {row.entryBand ? ` · ${row.entryBand}` : ''}
          </dd>
        </div>
        <div className="flex gap-2">
          <dt className="w-24 shrink-0 text-ink-mute">Exit</dt>
          <dd className="font-mono text-ink-soft">
            {row.exitDate ?? '—'}
            {final?.basis === 'measured' && !final.live ? ' · measured at close' : ''}
          </dd>
        </div>
        {row.continuedFrom ? (
          <div className="flex gap-2">
            <dt className="w-24 shrink-0 text-ink-mute">Continued</dt>
            <dd className="text-ink-soft">
              since {row.continuedFrom}
              {row.nBoards ? ` · ${row.nBoards} boards` : ''}
            </dd>
          </div>
        ) : null}
        {row.levelsUpdated ? (
          <div className="flex gap-2">
            <dt className="w-24 shrink-0 text-ink-mute">Levels</dt>
            <dd className="text-ink-soft">
              updated on this board
              {row.levelsUpdatedFrom ? ` (previous ${row.levelsUpdatedFrom})` : ''}
            </dd>
          </div>
        ) : null}
        {close.detail ? (
          <div className="flex gap-2">
            <dt className="w-24 shrink-0 text-ink-mute">Reason</dt>
            <dd className="text-ink-soft">{close.detail}</dd>
          </div>
        ) : null}
      </dl>
    </section>
  );
}

/**
 * The SSR-safe panel content: the lifecycle story, the full trade argument, and
 * the source-brief links. Split from the Sheet chrome (whose portal does not
 * render under static export) so tests can target it directly.
 */
export function IdeaPanelBody({
  idea,
  ideaEval,
}: {
  idea: FxTradeIdeaRow | null;
  ideaEval: FxIdeaEvalRow[];
}) {
  const { openBrief } = useTwelveX();
  const historyRow = useMemo(
    () => (idea ? (assembleTradeHistory([idea], ideaEval)[0] ?? null) : null),
    [idea, ideaEval],
  );
  const citations = useMemo(() => parseCitations(idea?.citations), [idea?.citations]);

  if (!idea) {
    return <p className="text-sm text-ink-mute">Trade idea not found in this feed.</p>;
  }

  return (
    <>
      {historyRow ? <IdeaLifecycleBlock row={historyRow} /> : null}

      <IdeaDetail idea={idea} />

      {citations.length > 0 ? (
        <section aria-label="Source briefs">
          <h3 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-ink-mute">
            Source briefs
          </h3>
          <ul className="flex flex-col gap-1">
            {citations.map((c, i) => (
              <li key={`${c.source_file ?? c.broker}-${i}`}>
                {c.source_file ? (
                  <Button
                    type="button"
                    variant="link"
                    size="xs"
                    className="h-auto justify-start p-0 text-left text-xs text-accent"
                    onClick={() => openBrief(c.source_file as string, null)}
                    title={c.broker ? `${c.broker} — ${c.source_file}` : c.source_file}
                  >
                    {c.broker ?? c.source_file}
                  </Button>
                ) : (
                  <span className="text-xs text-ink-soft">{c.broker}</span>
                )}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </>
  );
}

/**
 * Slide-over for one trade idea — the same shell as the broker-brief panel,
 * carrying the full argument (thesis, levels, market evidence, contributing
 * desks) plus the lifecycle outcome. Opened from a Trades row or a live idea
 * card; resolution is client-side from the already-loaded archive + evals.
 */
export default function IdeaPanel({
  open,
  runDate,
  rank,
  ideas,
  ideaEval,
  onClose,
}: {
  open: boolean;
  runDate: string | null;
  rank: number | null;
  ideas: FxTradeIdeaRow[];
  ideaEval: FxIdeaEvalRow[];
  onClose: () => void;
}) {
  const [size, setSize] = useState<DetailPanelSize>('default');

  const idea =
    runDate === null || rank === null
      ? null
      : (ideas.find((r) => r.run_date === runDate && r.rank === rank) ?? null);

  // Adjusting render-phase state (BriefPanel does the same) keeps the size
  // selection from leaking into the next panel opening.
  if (!open && size !== 'default') setSize('default');
  if (!open) return null;

  const title = idea ? idea.title || `${idea.pair} ${biasLabel(idea.direction)}` : 'Trade idea';
  const subtitle = idea
    ? `${idea.pair} · ${biasLabel(idea.direction)} · ${idea.run_date} #${idea.rank}`
    : `${runDate ?? '—'}${rank !== null ? ` #${rank}` : ''}`;
  const Icon = idea ? FileText : Target;

  return (
    <Sheet open onOpenChange={(next) => (next ? undefined : onClose())}>
      <SheetContent
        side="right"
        showCloseButton={false}
        className={`${detailPanelSheetSizeClass(size)} gap-0! bg-term-bg! shadow-2xl!`}
      >
        <div className="flex shrink-0 justify-center pt-2 sm:hidden" aria-hidden>
          <span className="h-1 w-9 bg-ink/20" />
        </div>
        <div className="flex items-start gap-3 border-b border-hair px-5 py-4">
          <Icon size={18} className="mt-0.5 shrink-0 text-accent" aria-hidden />
          <div className="min-w-0 flex-1">
            <SheetTitle className="truncate text-base font-semibold text-ink">{title}</SheetTitle>
            <p className="truncate font-mono text-[11px] text-ink-mute">{subtitle}</p>
          </div>
          <DetailPanelHeaderActions size={size} onSizeChange={setSize} onClose={onClose} />
        </div>

        <div
          className={[
            'min-h-0 flex-1 space-y-4 overflow-y-auto px-5 pt-4 pb-[max(1rem,env(safe-area-inset-bottom))]',
            size === 'full' ? 'md:mx-auto md:w-full md:max-w-3xl' : '',
          ].join(' ')}
        >
          <IdeaPanelBody idea={idea} ideaEval={ideaEval} />
        </div>
      </SheetContent>
    </Sheet>
  );
}
