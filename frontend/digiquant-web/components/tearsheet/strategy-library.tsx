"use client";

import { useMemo, useState } from "react";
import { SegToggle } from "./charts";
import { StrategyCard } from "./strategy-card";
import { cagrPctFromGrowth } from "./stats";
import { type StrategyIndexEntry } from "./types";

type SortKey = "cagr" | "profit_factor" | "max_drawdown" | "win_rate" | "trades";

type Enriched = StrategyIndexEntry & { cagr: number };

function enrich(entries: StrategyIndexEntry[]): Enriched[] {
  return entries.map((e) => ({
    ...e,
    cagr: cagrPctFromGrowth(e.net_profit_pct, e.period_start, e.period_end),
  }));
}

function sortEntries(items: Enriched[], key: SortKey): Enriched[] {
  const out = [...items];
  out.sort((a, b) => {
    switch (key) {
      case "cagr":
        return b.cagr - a.cagr;
      case "profit_factor":
        return (b.profit_factor ?? 0) - (a.profit_factor ?? 0);
      case "max_drawdown":
        return b.max_drawdown_pct - a.max_drawdown_pct;
      case "win_rate":
        return b.win_rate_pct - a.win_rate_pct;
      case "trades":
        return b.total_trades - a.total_trades;
      default:
        return 0;
    }
  });
  return out;
}

export function StrategyLibrary({ strategies }: { strategies: StrategyIndexEntry[] }) {
  const [sort, setSort] = useState<SortKey>("cagr");

  const visible = useMemo(
    () => sortEntries(enrich(strategies), sort),
    [strategies, sort],
  );

  return (
    <>
      <div className="ts-lib-toolbar">
        <SegToggle
          label="Sort by"
          value={sort}
          onChange={setSort}
          options={[
            { value: "cagr", label: "CAGR" },
            { value: "profit_factor", label: "Profit factor" },
            { value: "max_drawdown", label: "Max DD" },
            { value: "win_rate", label: "Win rate" },
            { value: "trades", label: "Trades" },
          ]}
        />
      </div>

      <section className="ts-lib-grid" aria-label="Published strategies">
        {visible.map((e) => (
          <StrategyCard key={e.strategy} e={e} />
        ))}
      </section>
    </>
  );
}
