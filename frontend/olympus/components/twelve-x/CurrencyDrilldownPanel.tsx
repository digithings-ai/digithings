'use client';

import { X } from 'lucide-react';
import { Sheet, SheetClose, SheetContent, SheetTitle } from '@digithings/web';

import type { ConsensusCurrencyRow } from '@/lib/twelve-x/consensus-view';
import type { FxBriefRow, IntelligenceWhyItem } from '@/lib/twelve-x/types';

function deskDirectionClasses(direction: string): { card: string; label: string } {
  const normalized = direction.trim().toLowerCase();
  if (normalized === 'bullish' || normalized === 'long' || normalized === 'buy') {
    return { card: 'border-accent/30 bg-accent/[0.05]', label: 'text-accent' };
  }
  if (normalized === 'bearish' || normalized === 'short' || normalized === 'sell') {
    return { card: 'border-warn/30 bg-warn/[0.05]', label: 'text-warn' };
  }
  return { card: 'border-hair bg-surface', label: 'text-ink-soft' };
}

/**
 * The loaded currency drilldown content (consensus metrics, confluence, desk
 * opinions, relevant briefs). Split from the panel chrome — the chrome is the
 * shared @digithings/web Sheet, whose portal never renders under static SSR,
 * so the SSR content test targets this component directly.
 */
export function CurrencyDrilldownPanelBody({
  currency,
  consensusRow,
  intelligenceItem,
  relevantBriefs,
  onOpenBrief,
}: {
  currency: string;
  consensusRow: ConsensusCurrencyRow;
  intelligenceItem: IntelligenceWhyItem | null;
  relevantBriefs: FxBriefRow[];
  onOpenBrief: (sourceFile: string, runDate: string | null) => void;
}) {
  const { actualNow, avgNow, priorChange, momentum, label } = consensusRow;

  // Confluence components
  const confluenceScore = intelligenceItem?.score ?? null;
  const components = intelligenceItem?.components;
  const consensus = intelligenceItem?.consensus;
  const activeDesks = (intelligenceItem?.desks ?? []).filter(
    (desk) => desk.classification.trim().toLowerCase() === 'active',
  );

  const formatScore = (v: number | null) => (v !== null && Number.isFinite(v) ? v.toFixed(2) : '—');
  const formatPct = (v: number | null) =>
    v !== null && Number.isFinite(v) ? `${Math.round(v <= 1 ? v * 100 : v)}%` : '—';

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="space-y-2">
        <h3 className="font-display text-2xl tracking-tight text-ink">{currency}</h3>
        <p className="text-sm text-ink-soft">{label}</p>
      </div>

      {/* Score metrics */}
      <div className="space-y-3 rounded-lg border border-hair bg-term-bg p-4">
        <h4 className="text-xs font-semibold uppercase tracking-wider text-ink-mute">
          Consensus Metrics
        </h4>
        <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
          <div>
            <dt className="text-ink-mute">Current score</dt>
            <dd className="font-mono text-ink">{formatScore(actualNow)}</dd>
          </div>
          <div>
            <dt className="text-ink-mute">5-run average</dt>
            <dd className="font-mono text-ink">{formatScore(avgNow)}</dd>
          </div>
          <div>
            <dt className="text-ink-mute">Prior-run change</dt>
            <dd className="font-mono text-ink">{formatScore(priorChange)}</dd>
          </div>
          <div>
            <dt className="text-ink-mute">Momentum</dt>
            <dd className="font-mono text-ink">{formatScore(momentum)}</dd>
          </div>
        </dl>
      </div>

      {/* Opinion counts and split */}
      {consensus && (
        <div className="space-y-3 rounded-lg border border-hair bg-term-bg p-4">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-ink-mute">
            Desk Opinions
          </h4>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
            <div>
              <dt className="text-ink-mute">Total views</dt>
              <dd className="font-mono text-ink">{consensus.n_views}</dd>
            </div>
            <div>
              <dt className="text-ink-mute">Desks</dt>
              <dd className="font-mono text-ink">{consensus.n_brokers}</dd>
            </div>
            <div>
              <dt className="text-ink-mute">Bullish</dt>
              <dd className="font-mono text-accent">{formatPct(consensus.bullish_pct)}</dd>
            </div>
            <div>
              <dt className="text-ink-mute">Bearish</dt>
              <dd className="font-mono text-warn">{formatPct(consensus.bearish_pct)}</dd>
            </div>
            <div>
              <dt className="text-ink-mute">Agreement</dt>
              <dd className="font-mono text-ink">{formatPct(consensus.agreement)}</dd>
            </div>
            <div>
              <dt className="text-ink-mute">Tilt</dt>
              <dd className="font-mono text-ink">{formatScore(consensus.tilt)}</dd>
            </div>
          </dl>
        </div>
      )}

      {/* Confluence score and components */}
      <div className="space-y-3 rounded-lg border border-hair bg-term-bg p-4">
        <h4 className="text-xs font-semibold uppercase tracking-wider text-ink-mute">
          Confluence
        </h4>
        <div className="space-y-2">
          <div>
            <span className="text-sm text-ink-mute">Score: </span>
            <span className="font-mono text-sm text-ink">{formatScore(confluenceScore)}</span>
          </div>
          {components && (
            <dl className="space-y-1 text-xs">
              <div className="flex justify-between">
                <dt className="text-ink-mute">Consensus strength</dt>
                <dd className="font-mono text-ink">{formatScore(components.consensus_strength)}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-ink-mute">Event alignment</dt>
                <dd className="font-mono text-ink">{formatScore(components.event_alignment)}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-ink-mute">Recency</dt>
                <dd className="font-mono text-ink">{formatScore(components.recency)}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-ink-mute">Breadth</dt>
                <dd className="font-mono text-ink">{formatScore(components.breadth)}</dd>
              </div>
            </dl>
          )}
        </div>
      </div>

      {/* Scrollable desk opinions */}
      {activeDesks.length > 0 && (
        <div className="space-y-3">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-ink-mute">
            Desk Opinions
          </h4>
          <div className="max-h-48 space-y-2 overflow-y-auto overscroll-contain pr-1 pb-1">
            {activeDesks.map((desk, i) => {
              const directionClasses = deskDirectionClasses(desk.direction);
              return (
                <div
                  key={i}
                  className={`rounded-lg border p-3 text-sm ${directionClasses.card}`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-ink">{desk.broker}</span>
                    <span className={`text-xs capitalize ${directionClasses.label}`}>
                      {desk.direction}
                    </span>
                  </div>
                  {desk.reason && <p className="mt-1 text-xs text-ink-mute">{desk.reason}</p>}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Scrollable relevant briefs */}
      {relevantBriefs.length > 0 && (
        <div className="space-y-3">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-ink-mute">
            Relevant Briefs
          </h4>
          <div className="max-h-48 space-y-2 overflow-y-auto overscroll-contain pr-1 pb-1">
            {relevantBriefs.map((brief) => (
              <button
                key={`${brief.source_file}-${brief.run_date}`}
                type="button"
                onClick={() => onOpenBrief(brief.source_file, brief.run_date)}
                className="w-full rounded-lg border border-hair bg-surface p-3 text-left text-sm transition-colors hover:border-accent hover:bg-surface/80"
              >
                <div className="font-medium text-ink">{brief.broker_name}</div>
                <div className="mt-1 text-xs text-ink-mute">{brief.central_thesis}</div>
                <div className="mt-1 font-mono text-xs text-ink-soft">{brief.source_file}</div>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * Currency drilldown panel — triggered by clicking a Consensus table row or
 * Details. Implemented as a Digiweb Sheet (same grammar as BriefPanel).
 * Shows score explanation, consensus metrics, desk opinions, confluence, and
 * relevant briefs. Brief buttons call the shared context `openBrief`.
 */
export default function CurrencyDrilldownPanel({
  open,
  onClose,
  currency,
  consensusRow,
  intelligenceItem,
  relevantBriefs,
  onOpenBrief,
}: {
  open: boolean;
  onClose: () => void;
  currency: string | null;
  consensusRow: ConsensusCurrencyRow | null;
  intelligenceItem: IntelligenceWhyItem | null;
  relevantBriefs: FxBriefRow[];
  onOpenBrief: (sourceFile: string, runDate: string | null) => void;
}) {
  if (!currency || !consensusRow) return null;

  return (
    <Sheet open={open} onOpenChange={(o) => !o && onClose()}>
      <SheetContent
        side="right"
        showCloseButton={false}
        className="flex w-full! max-w-lg! flex-col gap-0 bg-term-bg p-0 shadow-2xl"
      >
        <div className="flex shrink-0 items-center justify-between border-b border-hair px-5 py-4">
          <SheetTitle className="font-display text-lg tracking-tight text-ink">
            {currency} Details
          </SheetTitle>
          <SheetClose
            className="-mr-1.5 flex h-9 w-9 items-center justify-center rounded-lg text-ink-mute transition-colors hover:bg-ink/[0.06] hover:text-ink"
            aria-label="Close"
          >
            <X size={18} />
          </SheetClose>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 pt-4 pb-[max(1rem,env(safe-area-inset-bottom))]">
          <CurrencyDrilldownPanelBody
            currency={currency}
            consensusRow={consensusRow}
            intelligenceItem={intelligenceItem}
            relevantBriefs={relevantBriefs}
            onOpenBrief={(sourceFile, runDate) => {
              onClose();
              onOpenBrief(sourceFile, runDate);
            }}
          />
        </div>
      </SheetContent>
    </Sheet>
  );
}
