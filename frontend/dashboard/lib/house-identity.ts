/**
 * digithings house-book product chrome (#2643 / #1945 Track C).
 *
 * Declares the always-on ETF paper book identity and the Corpus | Book | Profile
 * contract until Track B ProfileConfig DB pins land. Read-only only — no editable
 * Settings surface here.
 */

export type HouseChromeTabId = 'corpus' | 'book' | 'profile';

export const HOUSE_CHROME_TABS: readonly {
  id: HouseChromeTabId;
  label: string;
  href: string;
}[] = [
  { id: 'corpus', label: 'Corpus', href: '/house?tab=corpus' },
  { id: 'book', label: 'Book', href: '/house?tab=book' },
  { id: 'profile', label: 'Profile', href: '/house?tab=profile' },
] as const;

/** Visible product identity for the digithings-owned house run. */
export const HOUSE_BOOK_IDENTITY = {
  owner: 'digithings',
  label: 'House ETF paper book',
  cadence: 'Always-on house run (immutable baseline)',
  summary:
    'Shared research corpus is tenant-agnostic; profiles may request extra work but cannot move, cancel, or replace the house run.',
} as const;

/**
 * Read-only house profile pins. Track B will replace static values with
 * DB-backed ProfileConfig; chrome must stay honest until then.
 */
export const HOUSE_PROFILE_PINS = {
  profileId: 'house',
  editable: false,
  universe: 'ETF house universe (declared)',
  riskStance: 'Paper book — no live-trading path',
  themes: 'Shared corpus themes (theme: / asset: / segment:)',
  note: 'Editable profile Settings wait on ProfileConfig (Track B). These pins are read-only chrome.',
} as const;

/** Tenant-agnostic corpus key prefixes (vision brief §4). */
export const CORPUS_KEY_PREFIXES = ['theme:', 'asset:', 'segment:'] as const;

export type PeriodInspectabilityState =
  | 'public_period_status_view'
  | 'empty_public_period_status'
  | 'query_failed'
  | 'unconfigured'
  | 'typed-gap-private-base-tables';

/**
 * Anon dashboard must not SELECT private `dashboard_accounting_*` base tables.
 * Curated tip status is available via `public_accounting_period_status` (#2599 / #2652).
 * Callers should load that view and map the result; this helper labels the contract.
 */
export function periodInspectabilityState(
  loadKind?: 'ok' | 'empty' | 'query_failed' | 'unconfigured'
): PeriodInspectabilityState {
  if (loadKind === 'ok') return 'public_period_status_view';
  if (loadKind === 'empty') return 'empty_public_period_status';
  if (loadKind === 'query_failed') return 'query_failed';
  if (loadKind === 'unconfigured') return 'unconfigured';
  // Default contract note when no load has run yet: private bases stay closed;
  // public tip view is the intended read path.
  return 'typed-gap-private-base-tables';
}

export function mapHouseTabFromUrl(raw: string | null): HouseChromeTabId {
  const value = (raw ?? 'corpus').toLowerCase();
  if (value === 'book' || value === 'profile' || value === 'corpus') return value;
  return 'corpus';
}

/** Classify a document path/key as shared-corpus-shaped (prefix match). */
export function isSharedCorpusKey(key: string): boolean {
  const trimmed = key.trim().toLowerCase();
  return CORPUS_KEY_PREFIXES.some((prefix) => trimmed.startsWith(prefix));
}
