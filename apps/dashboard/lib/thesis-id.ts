/**
 * Interim, clearly-labelled query-layer normalization (F4). Durable fix is
 * upstream (canonicalize `positions.thesis_id` to match `theses.thesis_id` —
 * backend issue). Until then: bare-ticker compare so a position keyed `ewt`
 * matches a thesis keyed `vehicle-ewt` or the live typo `veicle-ewt`, and case
 * is irrelevant.
 */
export function normalizeThesisId(id: string | null | undefined): string {
  return String(id ?? '')
    .trim()
    .toUpperCase()
    .replace(/^VEH?ICLE-/, '');
}

export function thesisIdEquals(a: string | null | undefined, b: string | null | undefined): boolean {
  const left = normalizeThesisId(a);
  const right = normalizeThesisId(b);
  return Boolean(left && right && left === right);
}
