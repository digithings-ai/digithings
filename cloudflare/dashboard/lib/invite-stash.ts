/**
 * Persist an FX Hub invite from `?invite=` across the auth round-trip.
 * The hashed redeem itself stays on POST /access/redeem-invite (see invite-auto-redeem).
 */

export const FX_HUB_INVITE_STORAGE_KEY = 'dq.fx_hub.invite';
export const INVITE_QUERY_PARAM = 'invite';
/** Match digiquant/supabase/functions/_shared/invite.ts INVITE_MIN_CODE_LENGTH. */
export const INVITE_MIN_CODE_LENGTH = 10;

export type InviteStorage = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;

export function parseInviteQuery(search: string): string | null {
  const raw = search.startsWith('?') ? search.slice(1) : search;
  if (!raw.trim()) return null;
  const code = (new URLSearchParams(raw).get(INVITE_QUERY_PARAM) ?? '').trim();
  if (code.length < INVITE_MIN_CODE_LENGTH) return null;
  return code;
}

function resolveStorage(storage?: InviteStorage): InviteStorage | null {
  if (storage) return storage;
  try {
    if (typeof sessionStorage === 'undefined') return null;
    return sessionStorage;
  } catch {
    return null;
  }
}

export function peekStashedInvite(storage?: InviteStorage): string | null {
  const store = resolveStorage(storage);
  if (!store) return null;
  try {
    const code = (store.getItem(FX_HUB_INVITE_STORAGE_KEY) ?? '').trim();
    if (code.length < INVITE_MIN_CODE_LENGTH) return null;
    return code;
  } catch {
    return null;
  }
}

export function stashInviteCode(code: string, storage?: InviteStorage): string | null {
  const trimmed = code.trim();
  if (trimmed.length < INVITE_MIN_CODE_LENGTH) return null;
  const store = resolveStorage(storage);
  if (!store) return null;
  try {
    store.setItem(FX_HUB_INVITE_STORAGE_KEY, trimmed);
    return trimmed;
  } catch {
    return null;
  }
}

export function clearStashedInvite(storage?: InviteStorage): void {
  const store = resolveStorage(storage);
  if (!store) return;
  try {
    store.removeItem(FX_HUB_INVITE_STORAGE_KEY);
  } catch {
    /* private-mode sessionStorage can throw */
  }
}

export function stashInviteFromSearch(search: string, storage?: InviteStorage): string | null {
  const code = parseInviteQuery(search);
  if (!code) return null;
  return stashInviteCode(code, storage);
}

/** Drop `invite` from a path+search+hash string; leave every other query param. */
export function pathWithoutInviteParam(pathAndSearch: string): string {
  const hashIndex = pathAndSearch.indexOf('#');
  const hash = hashIndex >= 0 ? pathAndSearch.slice(hashIndex) : '';
  const withoutHash = hashIndex >= 0 ? pathAndSearch.slice(0, hashIndex) : pathAndSearch;
  const qIndex = withoutHash.indexOf('?');
  if (qIndex < 0) return pathAndSearch;
  const pathname = withoutHash.slice(0, qIndex);
  const params = new URLSearchParams(withoutHash.slice(qIndex + 1));
  if (!params.has(INVITE_QUERY_PARAM)) return pathAndSearch;
  params.delete(INVITE_QUERY_PARAM);
  const qs = params.toString();
  return `${pathname}${qs ? `?${qs}` : ''}${hash}`;
}
