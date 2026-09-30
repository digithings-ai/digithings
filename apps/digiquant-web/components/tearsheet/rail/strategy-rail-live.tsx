"use client";
/** Tearsheets band piece: a kit CardRail of live StrategyCards from the
 *  existing strategy seam (Supabase `strategy_tearsheets`). Nothing renders
 *  from fixtures: loading and empty both show the labelled skeleton rail. */
import { useEffect, useMemo, useState } from "react";
import { CardRail } from "@digithings/ui";
import { Badge } from "@digithings/ui/ui";
import { fetchStrategyIndex } from "@/lib/live/strategies";
import { BacktestOnlyChip } from "../honesty";
import { cagrPctFromGrowth } from "../stats";
import { StrategyCard } from "../strategy-card";
import { type StrategyIndexEntry } from "../types";
import { StrategyRailSkeleton } from "./strategy-rail-skeleton";

export function StrategyRailLive() {
  // null until the first fetch settles, so server HTML and first client render agree.
  const [strategies, setStrategies] = useState<StrategyIndexEntry[] | null>(null);

  useEffect(() => {
    let alive = true;
    void fetchStrategyIndex()
      .then((all) => {
        if (alive) setStrategies(all);
      })
      .catch(() => {
        if (alive) setStrategies([]);
      });
    return () => {
      alive = false;
    };
  }, []);

  const sorted = useMemo(
    () =>
      [...(strategies ?? [])].sort(
        (a, b) =>
          cagrPctFromGrowth(b.net_profit_pct, b.period_start, b.period_end) -
          cagrPctFromGrowth(a.net_profit_pct, a.period_start, a.period_end),
      ),
    [strategies],
  );

  const chips = (
    <div className="flex flex-wrap items-center gap-2">
      <Badge variant="outline" className="text-ink-soft">
        backtest · illustrative, in-sample
      </Badge>
      <BacktestOnlyChip />
    </div>
  );

  if (strategies === null) {
    return (
      <div className="grid gap-4">
        {chips}
        <StrategyRailSkeleton message="Loading published strategies…" />
      </div>
    );
  }
  if (sorted.length === 0) {
    return (
      <div className="grid gap-4">
        {chips}
        <StrategyRailSkeleton message="no strategies published in this build" />
      </div>
    );
  }

  return (
    <CardRail
      ariaLabel="Strategy tearsheets"
      header={chips}
      itemClassName="w-[min(82vw,20rem)]"
      prevLabel="Previous tearsheet"
      nextLabel="Next tearsheet"
    >
      {sorted.map((e) => (
        <div key={e.strategy} className="flex h-full flex-col gap-2">
          <StrategyCard e={e} />
          <p className="m-0 font-mono text-[0.65rem] text-ink-mute">
            in-sample {e.period_start} → {e.period_end} · not a forecast
          </p>
        </div>
      ))}
    </CardRail>
  );
}
