"use client";
/** Client wrapper that loads the strategy index live from Supabase (#1069) and
 *  feeds it to the presentational <StrategyLibrary/>. Keeps app/strategies/page
 *  a server component (static shell + metadata) while the data reads at runtime. */
import { useEffect, useState } from "react";
import { StrategyLibrary } from "./strategy-library";
import { type StrategyIndexEntry } from "./types";
import { fetchStrategyIndex } from "@/lib/live/strategies";

export function StrategyLibraryLive() {
  const [strategies, setStrategies] = useState<StrategyIndexEntry[]>([]);

  useEffect(() => {
    let alive = true;
    void fetchStrategyIndex().then((all) => {
      if (alive) setStrategies(all);
    });
    return () => {
      alive = false;
    };
  }, []);

  return <StrategyLibrary strategies={strategies} />;
}
