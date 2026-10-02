"use client";
/** Tearsheets band piece: a kit CardRail when the live store returns strategies.
 *  Until then, the known routes render with every statistic as an em dash. */
import { useEffect, useMemo, useState } from "react";
import { CardRail } from "@digithings/ui";
import { Badge } from "@digithings/ui/ui";
import { fetchStrategyIndex } from "@/lib/live/strategies";
import { BacktestOnlyChip } from "../honesty";
import { PUBLISHED_STRATEGIES } from "../published";
import { cagrPctFromGrowth } from "../stats";
import { StrategyCard } from "../strategy-card";
import { type StrategyIndexEntry } from "../types";
import { UnpublishedStrategyCard } from "../unpublished-strategy";

export function StrategyRailLive() {
  // Unconfigured builds render the dash cards immediately, so server HTML and
  // the first client paint agree. A configured read starts empty of numbers.
  const [strategies, setStrategies] = useState<StrategyIndexEntry[] | null>([]);

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

  if (strategies === null || sorted.length === 0) {
    const message =
      strategies === null
        ? "Reading published tearsheets. Statistics stay an em dash until that read returns."
        : "The official API has not published strategy statistics. They stay an em dash.";
    return (
      <div className="grid gap-4">
        {chips}
        <p role="status" className="m-0 font-mono text-[0.72rem] text-ink-soft">
          {message}
        </p>
        <ul aria-label="Unpublished strategies" className="m-0 grid list-none gap-4 p-0 md:grid-cols-2 xl:grid-cols-4">
          {PUBLISHED_STRATEGIES.map((s) => (
            <li key={s.id} className="min-w-0">
              <UnpublishedStrategyCard id={s.id} label={s.label} symbol={s.symbol} />
            </li>
          ))}
        </ul>
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
