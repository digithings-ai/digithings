'use client';

import { useMemo, useState } from 'react';
import { Grid3x3 } from 'lucide-react';

import { MATRIX_COLUMNS } from '@/lib/twelve-x/types';
import type { MatrixCell } from '@/lib/twelve-x/types';
import { directionStyle, formatTargets, convictionOpacity } from '@/lib/twelve-x/matrix-format';
import BrokerProfilePanel from './BrokerProfilePanel';

export default function MatrixTab({
  cells,
  onOpenBrief,
  initialSelectedBroker = null,
}: {
  cells: MatrixCell[];
  onOpenBrief: (sourceFile: string, runDate: string | null) => void;
  /** Pre-open a broker's profile (deterministic SSR / tests). */
  initialSelectedBroker?: string | null;
}) {
  // The broker whose profile slide-over is open (the "focus on one broker" drill-in).
  const [selectedBroker, setSelectedBroker] = useState<string | null>(initialSelectedBroker);
  // Brokers present (rows), alphabetical.
  const brokers = useMemo(
    () => [...new Set(cells.map((c) => c.broker))].sort((a, b) => a.localeCompare(b)),
    [cells]
  );

  // (broker, column) → cell lookup. getMatrix already keeps one freshest cell per
  // (broker, G10 column), so the column placement matches the Notion matrix.
  const byCell = useMemo(() => {
    const m = new Map<string, MatrixCell>();
    for (const c of cells) m.set(`${c.broker}|${c.column}`, c);
    return m;
  }, [cells]);

  const hasData = brokers.length > 0;

  // Sticky broker label column + one column per G10 currency (fixed 8).
  const gridTemplate = `minmax(150px, 220px) repeat(${MATRIX_COLUMNS.length}, minmax(72px, 1fr))`;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3 px-1">
        <Grid3x3 size={18} className="shrink-0 text-accent" aria-hidden />
        <h2 className="font-display text-2xl tracking-tight text-ink">Desk view matrix</h2>
        <span className="rounded bg-term-bg px-1.5 py-0.5 text-[10px] font-medium text-ink-mute">
          8 of 10 G10 · NOK/SEK omitted
        </span>
      </div>

      <p className="max-w-2xl px-1 text-xs text-ink-mute">
        Each desk&apos;s latest standing view per board currency (8 of G10 — NOK/SEK desk views appear
        in Consensus, not here) over a recent window — consolidated the same way as the
        Notion board: a pair files under its base currency (EUR/USD → EUR), shown as stated. Cells are
        colored by direction and shaded by conviction; click a cell to open its source brief, or a
        desk name to see that broker&apos;s full standing-view profile.
      </p>

      {hasData ? (
        <div className="glass-card overflow-hidden p-0">
          <div className="overflow-x-auto">
            <div role="table" className="min-w-[760px] text-sm" aria-label="Broker by currency view matrix">
              {/* Header row */}
              <div
                role="row"
                className="grid items-stretch border-b border-hair bg-term-bg"
                style={{ gridTemplateColumns: gridTemplate }}
              >
                <div
                  role="columnheader"
                  className="sticky left-0 z-10 bg-term-bg px-4 py-2.5 text-[10px] font-semibold uppercase tracking-wider text-ink-mute"
                >
                  Desk
                </div>
                {MATRIX_COLUMNS.map((ccy) => (
                  <div
                    key={ccy}
                    role="columnheader"
                    className="px-2 py-2.5 text-center font-mono text-[11px] font-semibold text-ink-soft"
                  >
                    {ccy}
                  </div>
                ))}
              </div>

              {/* Body rows */}
              <div role="rowgroup" className="divide-y divide-hair">
                {brokers.map((broker) => (
                  <div
                    key={broker}
                    role="row"
                    className="grid items-stretch"
                    style={{ gridTemplateColumns: gridTemplate }}
                  >
                    <div
                      role="rowheader"
                      className="sticky left-0 z-10 bg-term-bg"
                    >
                      <button
                        type="button"
                        onClick={() => setSelectedBroker(broker)}
                        className="flex w-full items-center gap-1.5 truncate px-4 py-2 text-left font-medium text-ink transition-colors hover:text-accent"
                        title={`${broker} — open desk profile`}
                      >
                        <span className="truncate">{broker}</span>
                      </button>
                    </div>
                    {MATRIX_COLUMNS.map((ccy) => {
                      const cell = byCell.get(`${broker}|${ccy}`);
                      if (!cell) {
                        return (
                          <div
                            key={ccy}
                            role="cell"
                            className="flex items-center justify-center px-1 py-2 text-ink-mute/40"
                            aria-label={`${broker} ${ccy}: no view`}
                          >
                            <span aria-hidden>·</span>
                          </div>
                        );
                      }
                      const s = directionStyle(cell.direction);
                      // A pair (e.g. EUR/USD filed under EUR) shows the instrument so it's
                      // never misread as an outright single-currency call.
                      const isPair = cell.currency.includes('/');
                      // Surface broker levels/thesis in the tooltip when the desk view carries them.
                      const levels = formatTargets(cell.targets);
                      const title = `${broker} · ${cell.currency} · ${cell.direction}${
                        cell.conviction ? ` (${cell.conviction})` : ''
                      }${cell.signal ? ` — ${cell.signal}` : ''} · ${cell.report_date ?? cell.run_date}${
                        levels ? `\nLevels: ${levels}` : ''
                      }${cell.rationale ? `\n${cell.rationale}` : ''} — open brief`;
                      return (
                        <div key={ccy} role="cell" className="p-1">
                          <button
                            type="button"
                            onClick={() => onOpenBrief(cell.source_file, cell.run_date)}
                            className={`flex h-full w-full flex-col items-center justify-center gap-0.5 rounded-md border ${s.bg} ${s.border} px-1 py-1.5 text-center transition-colors hover:border-accent/50 hover:bg-ink/[0.05]`}
                            style={{ opacity: convictionOpacity(cell.conviction) }}
                            title={title}
                          >
                            <span className={`text-sm leading-none ${s.text}`} aria-hidden>
                              {s.glyph}
                            </span>
                            {isPair ? (
                              <span className="font-mono text-[8px] leading-none text-ink-mute/80">
                                {cell.currency}
                              </span>
                            ) : null}
                            <span className="font-mono text-[9px] leading-none text-ink-mute/70">
                              {(cell.report_date ?? cell.run_date).slice(5)}
                            </span>
                          </button>
                        </div>
                      );
                    })}
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Legend */}
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 border-t border-hair bg-term-bg px-4 py-2.5 text-[11px] text-ink-mute">
            <span className="flex items-center gap-1.5">
              <span className="text-up" aria-hidden>▲</span> Bullish
            </span>
            <span className="flex items-center gap-1.5">
              <span className="text-down" aria-hidden>▼</span> Bearish
            </span>
            <span className="flex items-center gap-1.5">
              <span className="text-warn" aria-hidden>◆</span> Watch
            </span>
            <span className="flex items-center gap-1.5">
              <span className="text-ink-soft" aria-hidden>•</span> Neutral
            </span>
            <span className="ml-auto">Brighter = higher conviction · a pair sits under its base ccy</span>
          </div>
        </div>
      ) : (
        <div className="glass-card p-10 text-center text-sm text-ink-mute">
          No desk views available in the recent window.
        </div>
      )}

      {/* Single-broker drill-in: click a desk label → its full standing-view profile. */}
      <BrokerProfilePanel
        broker={selectedBroker}
        cells={cells}
        onClose={() => setSelectedBroker(null)}
        onOpenBrief={onOpenBrief}
      />
    </div>
  );
}
