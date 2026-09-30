/**
 * Pure derivation for the Book view: treemap composition (by ticker, category
 * or thesis, for the live book or a historical date), concentration, and the
 * activity-event mix. No React, no I/O.
 */
import type { DashboardPositionEvent, PositionHistoryRow, Thesis } from './types';
import type { ReconciledPosition } from './book-reconciliation';
import { categoryStackLabel, inferPortfolioCategory } from './portfolio-categories';
import { thesisStackLabel } from './portfolio-aggregates';
import { normalizeThesisId } from './thesis-id';

export type CompositionMode = 'ticker' | 'category' | 'thesis';

export const COMPOSITION_MODES: ReadonlyArray<{ value: CompositionMode; label: string }> = [
  { value: 'ticker', label: 'Ticker' },
  { value: 'category', label: 'Category' },
  { value: 'thesis', label: 'Thesis' },
];

export interface CompositionItem {
  id: string;
  label: string;
  /** Weight in percent of NAV. */
  value: number;
  /** Treemap tone override (cash is pinned to the lightest step). */
  tone?: number;
  detail?: string;
}

export const CASH_ITEM_ID = '_cash';

interface WeightedHolding {
  ticker: string;
  category: string | null | undefined;
  thesisIds: string[];
  weight: number;
}

function round1(n: number): number {
  return Math.round(n * 10) / 10;
}

function groupKey(h: WeightedHolding, mode: CompositionMode): string[] {
  if (mode === 'ticker') return [h.ticker.toUpperCase()];
  if (mode === 'category') return [inferPortfolioCategory(h.ticker, h.category)];
  const ids = h.thesisIds.map((id) => normalizeThesisId(id)).filter(Boolean);
  return ids.length ? ids : ['_unlinked'];
}

function labelFor(key: string, mode: CompositionMode, theses: readonly Thesis[]): string {
  if (mode === 'ticker') return key;
  if (mode === 'category') return categoryStackLabel(key);
  return thesisStackLabel(key, theses as Thesis[]);
}

function compose(
  holdings: WeightedHolding[],
  mode: CompositionMode,
  cashPct: number,
  theses: readonly Thesis[]
): CompositionItem[] {
  const totals = new Map<string, number>();
  for (const h of holdings) {
    if (!(h.weight > 0)) continue;
    const keys = groupKey(h, mode);
    const share = h.weight / keys.length; // a multi-thesis holding splits evenly
    for (const k of keys) totals.set(k, (totals.get(k) ?? 0) + share);
  }
  const items: CompositionItem[] = [...totals.entries()]
    .map(([id, value]) => ({
      id,
      label: labelFor(id, mode, theses),
      value,
      detail: `${round1(value)}%`,
    }))
    .sort((a, b) => b.value - a.value);
  if (cashPct > 0.05) {
    items.push({
      id: CASH_ITEM_ID,
      label: 'Cash',
      value: cashPct,
      tone: 0,
      detail: `${round1(cashPct)}%`,
    });
  }
  return items;
}

/** Composition of the live (reconciled) book. */
export function liveComposition(
  rows: readonly ReconciledPosition[],
  cashPct: number,
  mode: CompositionMode,
  theses: readonly Thesis[]
): CompositionItem[] {
  return compose(
    rows.map((r) => ({
      ticker: r.ticker,
      category: r.category,
      thesisIds: r.thesis_ids ?? [],
      weight: r.normalizedWeight,
    })),
    mode,
    cashPct,
    theses
  );
}

/** Composition of the book as stored on one history date (cash is whatever is left of 100%). */
export function historicalComposition(
  history: readonly PositionHistoryRow[],
  date: string,
  mode: CompositionMode,
  theses: readonly Thesis[]
): CompositionItem[] {
  const slice = history.filter((r) => r.date === date && r.ticker.toUpperCase() !== 'CASH');
  const byTicker = new Map<string, WeightedHolding>();
  for (const r of slice) {
    const prev = byTicker.get(r.ticker);
    if (prev) {
      prev.weight += r.weight_pct;
    } else {
      byTicker.set(r.ticker, {
        ticker: r.ticker,
        category: r.category,
        thesisIds: r.thesis_id ? [r.thesis_id] : [],
        weight: r.weight_pct,
      });
    }
  }
  const held = [...byTicker.values()];
  const heldSum = held.reduce((s, h) => s + Math.max(0, h.weight), 0);
  return compose(held, mode, Math.max(0, 100 - heldSum), theses);
}

export interface Concentration {
  top1: { ticker: string; weightPct: number } | null;
  top5Pct: number;
  /** 1 / sum(share^2) over the held names: how many equal-sized bets the book is worth. */
  effectiveN: number | null;
}

export function concentration(rows: readonly ReconciledPosition[]): Concentration {
  const held = rows.filter((r) => r.normalizedWeight > 0).sort((a, b) => b.normalizedWeight - a.normalizedWeight);
  if (held.length === 0) return { top1: null, top5Pct: 0, effectiveN: null };
  const total = held.reduce((s, r) => s + r.normalizedWeight, 0);
  const hhi = held.reduce((s, r) => s + (r.normalizedWeight / total) ** 2, 0);
  return {
    top1: { ticker: held[0].ticker, weightPct: held[0].normalizedWeight },
    top5Pct: held.slice(0, 5).reduce((s, r) => s + r.normalizedWeight, 0),
    effectiveN: hhi > 0 ? 1 / hhi : null,
  };
}

/** Text summary used by the treemap's sr-only caption context and tests. */
export function compositionSummary(items: readonly CompositionItem[], n = 5): string {
  if (items.length === 0) return 'No allocation to show.';
  return items
    .slice(0, n)
    .map((i) => `${i.label} ${round1(i.value)}%`)
    .join(', ');
}

export interface EventMixSegment {
  id: string;
  label: string;
  value: number;
}

const EVENT_LABEL: Record<DashboardPositionEvent['event'], string> = {
  OPEN: 'Open',
  ADD: 'Add',
  TRIM: 'Trim',
  EXIT: 'Exit',
  HOLD: 'Hold',
};

/** Count of each event kind, in a stable order, zero kinds dropped. */
export function eventMix(events: readonly DashboardPositionEvent[]): EventMixSegment[] {
  const counts = new Map<DashboardPositionEvent['event'], number>();
  for (const e of events) counts.set(e.event, (counts.get(e.event) ?? 0) + 1);
  return (['OPEN', 'ADD', 'TRIM', 'EXIT', 'HOLD'] as const)
    .filter((k) => (counts.get(k) ?? 0) > 0)
    .map((k) => ({ id: k, label: EVENT_LABEL[k], value: counts.get(k) as number }));
}

/** Weight vs target gap in percentage points; null when there is no target. */
export function weightGapPp(weight: number, target: number | null | undefined): number | null {
  if (target == null || !Number.isFinite(target)) return null;
  return weight - target;
}
