"use client";

/**
 * The digiquant band's live reads, as one mount-only hook (#4429 round 7).
 *
 * It answers "is the dashboard's own backend reachable from this page" and, when
 * it is, hands back the published NAV series, the benchmark leg and the strategy
 * index. The owner's ask was explicit: "wire the chart and the performance
 * metrics to the dashboard correctly ... they should share the same canonical
 * backend for getting all that data." This hook is that share; it reads nothing
 * else and opens no socket.
 *
 * Mount-only by design: `next.config.mjs` is `output: "export"`, so a read
 * during render would run at build time and bake a stale series into the bundle.
 * Nothing is fetched until the browser has the page.
 */
/* eslint-disable react-hooks/set-state-in-effect -- async fetch lifecycle (mirrors digiquant-web's useLivePortfolio) */
import { useEffect, useState } from "react";
import {
  BENCHMARK_TICKER,
  cagrPct,
  fetchBenchmark,
  fetchNav,
  fetchStrategies,
  isDcaStrategy,
  type NavPoint,
  type PricePoint,
  type StrategyRead,
} from "./portfolio";
import { supabase } from "./supabaseClient";

export type { NavPoint, PricePoint, StrategyRead };
export { BENCHMARK_TICKER, cagrPct, isDcaStrategy };

export interface LiveBandRead {
  /** True when the public Supabase env is present on this build. */
  configured: boolean;
  loading: boolean;
  /** A non-fatal read failure; the band falls back to its example series. */
  error: string | null;
  nav: NavPoint[];
  benchmark: PricePoint[];
  strategies: StrategyRead[];
}

const EMPTY: LiveBandRead = {
  configured: false,
  loading: false,
  error: null,
  nav: [],
  benchmark: [],
  strategies: [],
};

/**
 * @param slugs the strategy membership and card order to read, in band order
 */
export function useLiveBand(slugs: readonly string[]): LiveBandRead {
  const configured = Boolean(supabase);
  const [read, setRead] = useState<Omit<LiveBandRead, "configured">>({
    loading: configured,
    error: null,
    nav: [],
    benchmark: [],
    strategies: [],
  });

  // Membership is a module-scope constant at every call site; joining it keeps
  // the effect dep a stable primitive rather than a new array each render.
  const key = slugs.join(",");

  useEffect(() => {
    if (!supabase) {
      setRead({ loading: false, error: null, nav: [], benchmark: [], strategies: [] });
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const [nav, strategies] = await Promise.all([
          fetchNav(),
          fetchStrategies(key.split(",")),
        ]);
        if (cancelled) return;
        const benchmark = nav.length > 0 ? await fetchBenchmark(nav[0].date) : [];
        if (cancelled) return;
        setRead({ loading: false, error: null, nav, benchmark, strategies });
      } catch (error) {
        if (cancelled) return;
        setRead({
          loading: false,
          error: error instanceof Error ? error.message : "live read failed",
          nav: [],
          benchmark: [],
          strategies: [],
        });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [key]);

  if (!configured) return EMPTY;
  return { configured, ...read };
}
