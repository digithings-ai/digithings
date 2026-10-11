import { useEffect, useMemo, useRef, useState } from "react";
import type { DeskStore, DeskStoreState } from "./desk-store";

/**
 * React adapter over a desk store.
 *
 * Plain `useState` plus `useEffect` is used on purpose instead of
 * `useSyncExternalStore`: the terminal desk renders through a renderer that is
 * not React DOM, and the two hooks carry different guarantees there. The state
 * held here is only the re-render trigger, so the value a render reads is
 * always the store's own, never a copy that could go stale.
 *
 * The first render seeds from the store, so a page opened after the preload has
 * landed paints its values straight away: there is no frame in which the desk
 * shows `loading...` for data that is already cached.
 */
export function useDeskReads<T>(store: DeskStore<T>, routes: readonly string[]): Record<string, T | undefined> {
  const [state, setState] = useState<DeskStoreState<T>>(store.snapshot);
  const key = routes.join("|");
  const routesRef = useRef(routes);
  routesRef.current = routes;

  useEffect(() => {
    // A store swapped under us must not leave the previous store's reads up.
    // eslint-disable-next-line react-hooks/set-state-in-effect -- async read lifecycle: adopt the new store before subscribing
    setState(store.snapshot());
    const unsubscribe = store.subscribe((next) => setState(next));
    store.load(routesRef.current);
    return unsubscribe;
  }, [store, key]);

  return useMemo(() => {
    const reads: Record<string, T | undefined> = {};
    for (const route of routesRef.current) {
      const entry = state[route];
      reads[route] = entry === undefined ? store.get(route) : entry.value;
    }
    return reads;
    // The routes are addressed through `key`. Listing the array itself would
    // rebuild this object every render for any caller that passes a literal.
  }, [store, state, key]);
}
