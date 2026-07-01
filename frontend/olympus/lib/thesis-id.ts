/**
 * Interim, clearly-labelled query-layer normalization (F4). Durable fix is
 * upstream (canonicalize `positions.thesis_id` to match `theses.thesis_id` —
 * backend issue). Until then: bare-ticker compare so a position keyed `ewt`
 * matches a thesis keyed `vehicle-ewt`, and case is irrelevant.
 */
export function normalizeThesisId(id: string | null | undefined): string {
  return String(id ?? '')
    .trim()
    .toUpperCase()
    .replace(/^VEHICLE-/, '');
}

export function thesisIdEquals(a: string | null | undefined, b: string | null | undefined): boolean {
  const left = normalizeThesisId(a);
  const right = normalizeThesisId(b);
  return Boolean(left && right && left === right);
}

/** Positions whose thesis_ids express `thesisId` under the normalized join. */
export function joinPositionsToThesis<T extends { thesis_ids: string[] }>(
  positions: T[],
  thesisId: string | null | undefined
): T[] {
  if (!thesisId) return [];
  return positions.filter((p) => p.thesis_ids.some((id) => thesisIdEquals(id, thesisId)));
}
