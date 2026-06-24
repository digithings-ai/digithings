'use client';

import { useMemo } from 'react';
import { Grid3x3 } from 'lucide-react';

import { MATRIX_COLUMNS } from '@/lib/twelve-x/types';
import type { MatrixCell } from '@/lib/twelve-x/types';

/** Map a currency-view direction to a .fin-* color + glyph for the matrix cell. */
function directionStyle(direction: string): { text: string; bg: string; border: string; glyph: string } {
  const d = direction.trim().toLowerCase();
  if (d === 'bullish' || d === 'long' || d === 'buy')
    return { text: 'text-fin-green', bg: 'bg-fin-green/10', border: 'border-fin-green/30', glyph: '▲' };
  if (d === 'bearish' || d === 'short' || d === 'sell')
    return { text: 'text-fin-red', bg: 'bg-fin-red/10', border: 'border-fin-red/30', glyph: '▼' };
  if (d === 'watch')
    return { text: 'text-fin-amber', bg: 'bg-fin-amber/10', border: 'border-fin-amber/30', glyph: '◆' };
  return { text: 'text-text-secondary', bg: 'bg-white/[0.03]', border: 'border-border-subtle', glyph: '•' };
}

/** Flatten a cell's broker targets (unknown[]) into a short, human-readable string. */
function formatTargets(targets: unknown[] | undefined): string | null {
  if (!targets || targets.length === 0) return null;
  const parts = targets
    .map((t) => {
      if (typeof t === 'string' || typeof t === 'number') return String(t);
      if (t && typeof t === 'object') {
        const o = t as Record<string, unknown>;
        const label = typeof o.label === 'string' ? o.label : typeof o.type === 'string' ? o.type : null;
        const level =
          typeof o.level === 'number' || typeof o.level === 'string'
            ? String(o.level)
            : typeof o.value === 'number' || typeof o.value === 'string'
              ? String(o.value)
              : typeof o.price === 'number' || typeof o.price === 'string'
                ? String(o.price)
                : null;
        if (label && level) return `${label} ${level}`;
        return level ?? label;
      }
      return null;
    })
    .filter((p): p is string => !!p);
  return parts.length > 0 ? parts.join(', ') : null;
}

/** Conviction → opacity weight so high-conviction cells read louder. */
function convictionOpacity(conviction: string): number {
  const c = conviction.trim().toLowerCase();
  if (c === 'high') return 1;
  if (c === 'medium' || c === 'mid') return 0.85;
  if (c === 'low') return 0.65;
  return 0.78;
}

export default function MatrixTab({
  cells,
  onOpenBrief,
}: {
  cells: MatrixCell[];
  onOpenBrief: (sourceFile: string, runDate: string | null) => void;
}) {
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
        <Grid3x3 size={18} className="shrink-0 text-fin-blue" aria-hidden />
        <h2 className="text-base font-semibold text-text-primary md:text-lg">Desk view matrix</h2>
        <span className="rounded bg-bg-secondary px-1.5 py-0.5 text-[10px] font-medium text-text-muted">
          8 of 10 G10 · NOK/SEK omitted
        </span>
      </div>

      <p className="max-w-2xl px-1 text-xs text-text-muted">
        Each desk&apos;s latest standing view per board currency (8 of G10 — NOK/SEK desk views appear
        in Consensus, not here) over a recent window — consolidated the same way as the
        Notion board: a pair files under its base currency (EUR/USD → EUR), shown as stated. Cells are
        colored by direction and shaded by conviction; click any cell to open the source brief.
      </p>

      {hasData ? (
        <div className="glass-card overflow-hidden p-0">
          <div className="overflow-x-auto">
            <div role="table" className="min-w-[760px] text-sm" aria-label="Broker by currency view matrix">
              {/* Header row */}
              <div
                role="row"
                className="grid items-stretch border-b border-border-subtle bg-bg-secondary"
                style={{ gridTemplateColumns: gridTemplate }}
              >
                <div
                  role="columnheader"
                  className="sticky left-0 z-10 bg-bg-secondary px-4 py-2.5 text-[10px] font-semibold uppercase tracking-wider text-text-muted"
                >
                  Desk
                </div>
                {MATRIX_COLUMNS.map((ccy) => (
                  <div
                    key={ccy}
                    role="columnheader"
                    className="px-2 py-2.5 text-center font-mono text-[11px] font-semibold text-text-secondary"
                  >
                    {ccy}
                  </div>
                ))}
              </div>

              {/* Body rows */}
              <div role="rowgroup" className="divide-y divide-border-subtle">
                {brokers.map((broker) => (
                  <div
                    key={broker}
                    role="row"
                    className="grid items-stretch"
                    style={{ gridTemplateColumns: gridTemplate }}
                  >
                    <div
                      role="rowheader"
                      className="sticky left-0 z-10 flex items-center truncate bg-bg-secondary px-4 py-2 font-medium text-text-primary"
                      title={broker}
                    >
                      <span className="truncate">{broker}</span>
                    </div>
                    {MATRIX_COLUMNS.map((ccy) => {
                      const cell = byCell.get(`${broker}|${ccy}`);
                      if (!cell) {
                        return (
                          <div
                            key={ccy}
                            role="cell"
                            className="flex items-center justify-center px-1 py-2 text-text-muted/40"
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
                            className={`flex h-full w-full flex-col items-center justify-center gap-0.5 rounded-md border ${s.bg} ${s.border} px-1 py-1.5 text-center transition-colors hover:border-fin-blue/50 hover:bg-white/[0.05]`}
                            style={{ opacity: convictionOpacity(cell.conviction) }}
                            title={title}
                          >
                            <span className={`text-sm leading-none ${s.text}`} aria-hidden>
                              {s.glyph}
                            </span>
                            {isPair ? (
                              <span className="font-mono text-[8px] leading-none text-text-muted/80">
                                {cell.currency}
                              </span>
                            ) : null}
                            <span className="font-mono text-[9px] leading-none text-text-muted/70">
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
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 border-t border-border-subtle bg-bg-secondary px-4 py-2.5 text-[11px] text-text-muted">
            <span className="flex items-center gap-1.5">
              <span className="text-fin-green" aria-hidden>▲</span> Bullish
            </span>
            <span className="flex items-center gap-1.5">
              <span className="text-fin-red" aria-hidden>▼</span> Bearish
            </span>
            <span className="flex items-center gap-1.5">
              <span className="text-fin-amber" aria-hidden>◆</span> Watch
            </span>
            <span className="flex items-center gap-1.5">
              <span className="text-text-secondary" aria-hidden>•</span> Neutral
            </span>
            <span className="ml-auto">Brighter = higher conviction · a pair sits under its base ccy</span>
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
