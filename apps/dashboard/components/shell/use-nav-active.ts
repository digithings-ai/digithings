'use client';

import { useSyncExternalStore } from 'react';
import { usePathname } from 'next/navigation';
import { dashboardBasePath } from '@/lib/supabase';
import { normalizePath } from './nav-model';

/**
 * Pages mirror in-page state into the URL with history.replaceState, which
 * fires no event; they (and the sidebar's own child links) dispatch this so
 * the sidebar re-reads `location.search` / `location.hash`.
 */
export const URLSTATE_EVENT = 'dashboard:urlstate';

export function notifyUrlState() {
  if (typeof window !== 'undefined') window.dispatchEvent(new Event(URLSTATE_EVENT));
}

function subscribe(cb: () => void) {
  window.addEventListener('hashchange', cb);
  window.addEventListener('popstate', cb);
  window.addEventListener(URLSTATE_EVENT, cb);
  return () => {
    window.removeEventListener('hashchange', cb);
    window.removeEventListener('popstate', cb);
    window.removeEventListener(URLSTATE_EVENT, cb);
  };
}

const snapshot = () => `${window.location.search}\u0000${window.location.hash}`;
const serverSnapshot = () => '\u0000';

/** Current route state for nav highlighting; SSR renders parent-only (empty query/hash). */
export function useNavActive(): { path: string; search: string; hash: string } {
  const pathname = usePathname();
  const raw = useSyncExternalStore(subscribe, snapshot, serverSnapshot);
  const [search, hash] = raw.split('\u0000');
  return { path: normalizePath(pathname, dashboardBasePath()), search: search ?? '', hash: hash ?? '' };
}
