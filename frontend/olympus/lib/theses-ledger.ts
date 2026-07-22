import { thesisIdEquals } from './thesis-id';
import type { Thesis } from './types';

/** Two-tier split: explicit 'vehicle' kind → vehicle; everything else → market. */
export function splitTheses(theses: Thesis[]): { market: Thesis[]; vehicle: Thesis[] } {
  const market: Thesis[] = [];
  const vehicle: Thesis[] = [];
  for (const t of theses) {
    if ((t.thesis_kind ?? '').toLowerCase() === 'vehicle') vehicle.push(t);
    else market.push(t);
  }
  return { market, vehicle };
}

/** Confidence descending; null confidence sorted last; ties broken by name for stability. */
export function sortByConfidenceDesc(theses: Thesis[]): Thesis[] {
  return [...theses].sort((a, b) => {
    const ca = a.confidence;
    const cb = b.confidence;
    if (ca == null && cb == null) return a.name.localeCompare(b.name);
    if (ca == null) return 1;
    if (cb == null) return -1;
    if (cb !== ca) return cb - ca;
    return a.name.localeCompare(b.name);
  });
}

/** Keep one research view per durable topic, preferring the highest-conviction row. */
export function consolidateThesesByTopic(theses: Thesis[]): Thesis[] {
  const consolidated = new Map<string, Thesis>();
  for (const thesis of sortByConfidenceDesc(theses)) {
    const key = thesis.topic_key?.trim().toLowerCase() || `id:${thesis.id}`;
    if (!consolidated.has(key)) consolidated.set(key, thesis);
  }
  return [...consolidated.values()];
}

export interface VehicleThesisGroup {
  marketId: string | null;
  marketName: string | null;
  theses: Thesis[];
}

/** Group vehicle theses under their linked market thesis; unmatched/null land in a trailing unlinked group. */
export function groupVehicleTheses(vehicle: Thesis[], market: Thesis[]): VehicleThesisGroup[] {
  const sortedMarket = sortByConfidenceDesc(market);
  const linked = new Map<string, Thesis[]>();
  const unlinked: Thesis[] = [];
  for (const v of vehicle) {
    const parent = v.linked_market_thesis_id
      ? sortedMarket.find((m) => thesisIdEquals(m.id, v.linked_market_thesis_id)) ?? null
      : null;
    if (!parent) {
      unlinked.push(v);
      continue;
    }
    if (!linked.has(parent.id)) linked.set(parent.id, []);
    linked.get(parent.id)!.push(v);
  }
  const groups: VehicleThesisGroup[] = [];
  for (const m of sortedMarket) {
    const rows = linked.get(m.id);
    if (rows && rows.length) {
      groups.push({ marketId: m.id, marketName: m.name, theses: rows });
    }
  }
  if (unlinked.length) {
    groups.push({ marketId: null, marketName: null, theses: unlinked });
  }
  return groups;
}

/** Normalized-id lookup (tolerant of `vehicle-`/case differences via thesisIdEquals). */
export function findThesisById(theses: Thesis[], id: string): Thesis | null {
  return theses.find((t) => thesisIdEquals(t.id, id)) ?? null;
}
