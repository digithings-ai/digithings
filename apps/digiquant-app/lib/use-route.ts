'use client';

import { useEffect, useState } from 'react';
import { dqGet, type Envelope } from './dq-api';

/** Blocks on one page share a route (e.g. /allocations x4): concurrent requests ride one fetch. */
const inflight = new Map<string, Promise<Envelope<unknown>>>();
function shared<T>(route: string): Promise<Envelope<T>> {
  let p = inflight.get(route);
  if (!p) {
    p = dqGet<unknown>(route);
    inflight.set(route, p);
    const done = () => { inflight.delete(route); };
    p.then(done, done);
  }
  return p as Promise<Envelope<T>>;
}

export type RouteState<T> = { env: Envelope<T> | null; err: string | null };

/** Fetch one DigiQuant API route. Errors surface as text; no fallback data. */
export function useRoute<T>(route: string): RouteState<T> {
  const [s, set] = useState<RouteState<T>>({ env: null, err: null });
  useEffect(() => {
    let live = true;
    set({ env: null, err: null });
    shared<T>(route)
      .then((env) => live && set({ env, err: null }))
      .catch((e: unknown) => live && set({ env: null, err: e instanceof Error ? e.message : 'failed' }));
    return () => { live = false; };
  }, [route]);
  return s;
}
