"use client";

import { useMemo, useState } from "react";
import { SegToggle } from "@digithings/web";
import { StrategyCard } from "./strategy-card";
import {
  matchesPublicType,
  publicTypeFilterOptions,
  type PublicTypeFilter,
} from "./strategy-kinds";
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
        return (b.win_rate_pct ?? 0) - (a.win_rate_pct ?? 0);
      case "trades":
        return b.total_trades - a.total_trades;
      default: {
        const _exhaustive: never = key;
        return _exhaustive;
      }
    }
  });
  return out;
}

export function filterLibrary(
  entries: StrategyIndexEntry[],
  typeFilter: PublicTypeFilter,
  sort: SortKey,
): Enriched[] {
  const typed = enrich(entries).filter((e) =>
    matchesPublicType(e.strategy, e.kind, typeFilter),
  );
  return sortEntries(typed, sort);
}

export function StrategyLibrary({
  strategies,
  loading = false,
}: {
  strategies: StrategyIndexEntry[];
  /** True until the first index fetch settles — renders a neutral loading
   *  state (identical server-side) instead of the honest-empty copy. */
  loading?: boolean;
}) {
  const [sort, setSort] = useState<SortKey>("cagr");
  const [typeFilter, setTypeFilter] = useState<PublicTypeFilter>("all");

  const visible = useMemo(
    () => filterLibrary(strategies, typeFilter, sort),
    [strategies, typeFilter, sort],
  );

  return (
    <>
      <div className="ts-lib-toolbar">
        <SegToggle
          label="Strategy type"
          value={typeFilter}
          onChange={setTypeFilter}
          options={publicTypeFilterOptions()}
        />
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

      {visible.length === 0 ? (
        <p className="dq-sub" role="status">
          {loading ? "Loading strategies…" : "No strategies of this type in the library."}
        </p>
      ) : (
        <section className="ts-lib-grid" aria-label="Published strategies">
          {visible.map((e) => (
            <StrategyCard key={e.strategy} e={e} />
          ))}
        </section>
      )}
    </>
  );
}
