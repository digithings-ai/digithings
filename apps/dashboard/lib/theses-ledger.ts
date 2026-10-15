import { thesisIdEquals } from './thesis-id';
import type { Thesis } from './types';

/** ``vehicle-{ticker}`` plus the live typo ``veicle-{ticker}`` (missing 'h'). */
const VEHICLE_SHAPED_ID = /^veh?icle-/i;

/** Vehicle-kind rows, or ids that are vehicles regardless of a null ``thesis_kind``. */
export function isVehicleThesis(thesis: Pick<Thesis, 'id' | 'thesis_kind'>): boolean {
  if ((thesis.thesis_kind ?? '').toLowerCase() === 'vehicle') return true;
  return VEHICLE_SHAPED_ID.test(thesis.id ?? '');
}

/** Two-tier split: vehicle kind / vehicle-shaped id → vehicle; everything else → market. */
export function splitTheses(theses: Thesis[]): { market: Thesis[]; vehicle: Thesis[] } {
  const market: Thesis[] = [];
  const vehicle: Thesis[] = [];
  for (const t of theses) {
    if (isVehicleThesis(t)) vehicle.push(t);
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

/** Normalized-id lookup (tolerant of `vehicle-`/case differences via thesisIdEquals). */
export function findThesisById(theses: Thesis[], id: string): Thesis | null {
  return theses.find((t) => thesisIdEquals(t.id, id)) ?? null;
}
