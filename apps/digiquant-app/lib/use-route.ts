'use client';

import { useEffect, useState } from 'react';
import { dqGet, type Envelope } from './dq-api';

export type RouteState<T> = { env: Envelope<T> | null; err: string | null };

/** Fetch one DigiQuant API route. Errors surface as text; no fallback data. */
export function useRoute<T>(route: string): RouteState<T> {
  const [s, set] = useState<RouteState<T>>({ env: null, err: null });
  useEffect(() => {
    let live = true;
    dqGet<T>(route)
      .then((env) => live && set({ env, err: null }))
      .catch((e: unknown) => live && set({ env: null, err: e instanceof Error ? e.message : 'failed' }));
    return () => { live = false; };
  }, [route]);
  return s;
}
