/**
 * Secretless worker doubles. Same markers the homepage uses
 * (`apps/digiquant-web/lib/official-api.ts`): stub NAV 99.909 / 204.04,
 * the paired return series, and `legacy_estimate`. A hit is withheld.
 */
export function isStubEnvelope(body: unknown): boolean {
  const text = JSON.stringify(body ?? null);
  if (text.includes('"legacy_estimate"')) return true;
  if (text.includes('99.909') || text.includes('204.04') || text.includes('204.040')) return true;
  if (text.includes('103.040192') || text.includes('104.44808') || text.includes('3.040191838399986')) return true;
  if (text.includes('"close":500') && text.includes('2026-08-20') && text.includes('"close":515')) return true;
  return false;
}

export const STUB_READ = 'The official API returned a stub envelope, not a house-book read.';
