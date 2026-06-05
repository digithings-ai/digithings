"use client";

import { useEffect, useState } from "react";

type AsyncDataState<T> = {
  loading: boolean;
  error: string | null;
  data: T;
};

/**
 * Shared fetch lifecycle for portfolio drilldowns (SIMP-028).
 * Replaces per-component set-state-in-effect eslint disables.
 */
export function useAsyncData<T>(
  initial: T,
  loader: (signal: AbortSignal) => Promise<T>,
  deps: readonly unknown[]
): AsyncDataState<T> {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<T>(initial);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    loader(controller.signal)
      .then((value) => {
        if (!controller.signal.aborted) setData(value);
      })
      .catch((e: unknown) => {
        if (!controller.signal.aborted) {
          setError(e instanceof Error ? e.message : "Failed to load");
          setData(initial);
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- caller supplies stable deps
  }, deps);

  return { loading, error, data };
}
