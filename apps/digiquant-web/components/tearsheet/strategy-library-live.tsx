"use client";
/** Client wrapper that loads the strategy index live from Supabase (#1069) and
 *  feeds it to the presentational <StrategyLibrary/>. Keeps app/strategies/page
 *  a server component (static shell + metadata) while the data reads at runtime. */
import { useEffect, useState } from "react";
import { StrategyLibrary } from "./strategy-library";
import { type StrategyIndexEntry } from "./types";
import { fetchStrategyIndex } from "@/lib/live/strategies";

export function StrategyLibraryLive() {
  // null until the first fetch settles: the static export prerenders the
  // loading state, so server HTML and the first client render agree (no
  // hydration mismatch); the honest-empty state only renders after a
  // completed load returns zero rows.
  const [strategies, setStrategies] = useState<StrategyIndexEntry[] | null>(null);

  useEffect(() => {
    let alive = true;
    void fetchStrategyIndex()
      .then((all) => {
        if (alive) setStrategies(all);
      })
      .catch(() => {
        // A throw must not stick on perpetual loading: fall through to the
        // honest-empty state (fetchStrategyIndex already returns [] for
        // known no-data cases; this covers aborts and network failures).
        if (alive) setStrategies([]);
      });
    return () => {
      alive = false;
    };
  }, []);

  return <StrategyLibrary strategies={strategies ?? []} loading={strategies === null} />;
}
