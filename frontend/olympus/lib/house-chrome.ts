/**
 * Track C product chrome contracts (#2644 / #1945 vision brief).
 *
 * Corpus + Profile pins live in service_role-only tables
 * (`olympus_research_corpus`, `olympus_profile_config`). The browser must not
 * invent rows when those tables are unreachable — show typed gaps instead.
 * The digithings house identity below matches migration 075 seed so Profile
 * chrome can label the always-on house pin without a private read.
 */

export type CorpusKeyKind = 'theme' | 'asset' | 'segment';

/** Migration 075 house seed — public product identity, not a live DB read. */
export const HOUSE_PROFILE_PIN = {
  versionId: '4ee97e91-7b5b-5a50-b562-37d34250b0f9',
  profileKey: 'house',
  schemaVersion: 1,
  isHouseDefault: true,
  label: 'digithings house',
} as const;

export const CORPUS_KEY_KINDS: readonly CorpusKeyKind[] = ['theme', 'asset', 'segment'];

export const CORPUS_KEY_PATTERN = /^(theme|asset|segment):[a-z0-9][a-z0-9._/-]{0,198}$/;

export type TypedChromeGap =
  | 'corpus_service_role_only'
  | 'profile_live_read_blocked'
  | 'period_empty'
  | 'period_query_failed'
  | 'ledger_empty';

export const TYPED_CHROME_GAP_COPY: Record<TypedChromeGap, string> = {
  corpus_service_role_only:
    'Shared research corpus pins (theme: / asset: / segment:) are stored in olympus_research_corpus with service_role-only access. No browser-readable public view ships yet — this chrome does not invent corpus rows.',
  profile_live_read_blocked:
    'Live olympus_profile_config rows are service_role-only. House pin identity below is the digithings migration seed (read-only chrome), not a live overlay catalog.',
  period_empty:
    'No tip rows in public_accounting_period_status yet. Period inspectability waits on finalized accounting writers — this is an empty evidence state, not a fabricated period.',
  period_query_failed:
    'Could not load public_accounting_period_status. Check Supabase connectivity; do not treat this as a successful empty book.',
  ledger_empty: 'No non-HOLD position events recorded for the current book.',
};

/** Validate a tenant-agnostic corpus key without inventing one. */
export function isValidCorpusKey(key: string): boolean {
  return CORPUS_KEY_PATTERN.test(key);
}

export function corpusKeyKind(key: string): CorpusKeyKind | null {
  if (!isValidCorpusKey(key)) return null;
  return key.split(':', 1)[0] as CorpusKeyKind;
}
