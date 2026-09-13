/**
 * Grouping for the relevance-ledger desk classes surfaced in the drilldown's
 * opposition ledger. The drilldown used to show ACTIVE desks only; the track
 * record work deliberately shows ALL lifecycle classes so superseded and
 * invalidated reads stay auditable instead of silently disappearing.
 */
import type { IntelligenceWhyDesk } from './types';

/** Canonical display order for known ledger lifecycle classes. */
export const LEDGER_CLASS_ORDER = ['active', 'confirmed', 'invalidated', 'superseded'] as const;

export type KnownLedgerClass = (typeof LEDGER_CLASS_ORDER)[number];

/** Normalize a raw classification value to its grouping key. */
export function normalizeLedgerClass(classification: string | null | undefined): string {
  const key = (classification ?? '').trim().toLowerCase();
  return key || 'unknown';
}

/** Human label for a ledger class key (`superseded` → `Superseded`). */
export function ledgerClassLabel(classification: string): string {
  const key = normalizeLedgerClass(classification);
  return key.charAt(0).toUpperCase() + key.slice(1);
}

export interface LedgerClassGroup {
  classification: string;
  label: string;
  desks: IntelligenceWhyDesk[];
}

/**
 * Bucket desks by ledger class. Known classes follow LEDGER_CLASS_ORDER;
 * unknown classes trail alphabetically. Desks keep their input order within a
 * group (callers pass relevance-descending). Input is not mutated.
 */
export function groupLedgerByClass(desks: IntelligenceWhyDesk[]): LedgerClassGroup[] {
  const buckets = new Map<string, IntelligenceWhyDesk[]>();
  for (const desk of desks) {
    const key = normalizeLedgerClass(desk.classification);
    const bucket = buckets.get(key);
    if (bucket) bucket.push(desk);
    else buckets.set(key, [desk]);
  }
  const known = LEDGER_CLASS_ORDER.filter((c) => buckets.has(c));
  const extra = [...buckets.keys()].filter((c) => !(LEDGER_CLASS_ORDER as readonly string[]).includes(c)).sort();
  return [...known, ...extra].map((classification) => ({
    classification,
    label: ledgerClassLabel(classification),
    desks: buckets.get(classification) ?? [],
  }));
}

/** Per-class desk counts in display order (for headers / summaries). */
export function countLedgerByClass(desks: IntelligenceWhyDesk[]): { classification: string; count: number }[] {
  return groupLedgerByClass(desks).map((g) => ({ classification: g.classification, count: g.desks.length }));
}
