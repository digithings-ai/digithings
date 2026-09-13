'use client';

import type { IntelligenceWhyDesk } from '@/lib/twelve-x/types';
import { groupLedgerByClass } from '@/lib/twelve-x/ledger-classes';

export function deskDirectionClasses(direction: string): { card: string; label: string } {
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
 * The full deliberation ledger for a currency: EVERY lifecycle class
 * (active, confirmed, invalidated, superseded, …), grouped in canonical order.
 * Superseded/invalidated reads are the opposition — they show what the street
 * used to think and why it changed, so they stay visible instead of hidden.
 */
export function OppositionLedger({ desks }: { desks: IntelligenceWhyDesk[] }) {
  const groups = groupLedgerByClass(desks);
  if (groups.length === 0) return null;

  return (
    <div className="space-y-3" data-testid="opposition-ledger">
      <h4 className="text-xs font-semibold uppercase tracking-wider text-ink-mute">
        Desk ledger · {desks.length}
      </h4>
      {groups.map((group) => (
        <div key={group.classification} className="space-y-2">
          <p className="font-mono text-[11px] uppercase tracking-wider text-ink-soft">
            {group.label} · {group.desks.length}
          </p>
          <div className="max-h-48 space-y-2 overflow-y-auto overscroll-contain pr-1 pb-1">
            {group.desks.map((desk, i) => {
              const directionClasses = deskDirectionClasses(desk.direction);
              return (
                <div
                  key={`${group.classification}-${desk.broker}-${i}`}
                  className={`rounded-none border p-3 text-sm ${directionClasses.card}`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium text-ink">{desk.broker}</span>
                    <span className={`text-xs capitalize ${directionClasses.label}`}>
                      {desk.direction}
                    </span>
                  </div>
                  <div className="mt-1 flex flex-wrap gap-x-3 font-mono text-[10px] text-ink-mute">
                    {desk.conviction ? <span>{desk.conviction}</span> : null}
                    <span>w {Number.isFinite(desk.relevance) ? desk.relevance.toFixed(2) : '—'}</span>
                  </div>
                  {desk.reason && <p className="mt-1 text-xs text-ink-mute">{desk.reason}</p>}
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}

export default OppositionLedger;
