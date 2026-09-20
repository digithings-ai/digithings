'use client';

import { useCallback, useEffect, useState } from 'react';

/** A localStorage-backed currency watchlist with an optional "filter on" toggle. */
export interface WatchlistApi {
  items: string[];
  has: (c: string) => boolean;
  toggle: (c: string) => void;
  clear: () => void;
  filterOn: boolean;
  setFilterOn: (b: boolean) => void;
}

/**
 * A small, SSR-safe watchlist hook. State lazy-inits to `[]` (never touches
 * localStorage during render/init); the stored value is hydrated in a mount
 * effect and persisted on change. All storage access is wrapped in try/catch.
 */
export function useWatchlist(storageKey = 'twelvex-watchlist'): WatchlistApi {
  const [items, setItems] = useState<string[]>([]);
  const [filterOn, setFilterOn] = useState(false);

  // Hydrate from storage on mount (client only).
  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(storageKey);
      if (!raw) return;
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) {
        // Hydrate-after-mount is intentional: lazy-initializing from localStorage
        // during render would cause an SSR/prerender hydration mismatch (server has
        // no storage). Setting state in this mount-only effect is the safe pattern.
        // eslint-disable-next-line react-hooks/set-state-in-effect
        setItems(parsed.map((x) => String(x)));
      }
    } catch {
      /* ignore unavailable / malformed storage */
    }
  }, [storageKey]);

  // Persist on change.
  useEffect(() => {
    try {
      window.localStorage.setItem(storageKey, JSON.stringify(items));
    } catch {
      /* ignore unavailable storage */
    }
  }, [storageKey, items]);

  const has = useCallback((c: string) => items.includes(c), [items]);

  const toggle = useCallback((c: string) => {
    setItems((prev) => (prev.includes(c) ? prev.filter((x) => x !== c) : [...prev, c]));
  }, []);

  const clear = useCallback(() => setItems([]), []);

  return { items, has, toggle, clear, filterOn, setFilterOn };
}
