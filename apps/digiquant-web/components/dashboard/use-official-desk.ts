"use client";

import { useEffect, useState } from "react";
import type { LivePerformanceKpis } from "@digithings/ui";
import { houseBookFromPayloads, officialGet, type OfficialHouseBook } from "@/lib/official-api";
import { createDeskCache } from "@/lib/live/desk-cache";
import type { LivePortfolioResult, LivePosition, NavPoint } from "@/lib/live/types";

type DeskInput = Pick<
  LivePortfolioResult,
  "loading" | "configured" | "error" | "navContractError" | "positions" | "nav" | "metricsAsOf" | "kpis"
>;

const READING: DeskInput = {
  loading: true,
  configured: true,
  error: null,
  navContractError: null,
  positions: [],
  nav: [],
  metricsAsOf: null,
  kpis: null,
};

function kpisFrom(book: OfficialHouseBook): LivePerformanceKpis {
  return {
    liveNav: null,
    liveVsMarkPct: 0,
    priceAsOfDate: book.priceAsOfDate,
    dayReturnPct: book.dayReturnPct,
    sinceInceptionPct: book.sinceInceptionPct,
    sinceInceptionStartDate: null,
    portfolioReturnPct: book.sinceInceptionPct,
    benchmarkReturnPct: null,
    excessReturnPct: book.excessReturnPct,
    relativeGainPct: book.excessReturnPct,
    alphaPct: null,
    informationRatio: null,
    benchmarkTicker: book.benchmarkTicker,
    bookNavDate: book.asOf,
  };
}

function toPosition(row: OfficialHouseBook["positions"][number]): LivePosition {
  return {
    ticker: row.ticker,
    name: null,
    category: null,
    sectorBucket: null,
    weightPct: row.weightPct ?? Number.NaN,
    entryPrice: row.entryPrice,
    entryDate: null,
    currentPrice: row.currentPrice,
    dayChangePct: row.dayChangePct,
    unrealizedPnlPct: row.unrealizedPnlPct,
    sinceEntryReturnPct: null,
    metricsAsOf: null,
    livePrice: row.currentPrice,
    isLive: false,
  };
}

function toNav(book: OfficialHouseBook): NavPoint[] {
  return book.nav.map((p) => ({
    date: p.date,
    nav: p.nav,
    cashPct: null,
    investedPct: null,
    dayReturnPct: p.dayReturnPct,
    contract: p.contract,
  }));
}

/**
 * One read per dataset per window, shared by every mount of this hook.
 *
 * Module scope on purpose: the desk, the brief drawer and a route change each mount their own
 * copy of this hook, and a store created inside the component would be thrown away with it —
 * which is the fetch-on-every-mount behaviour this replaces.
 */
const DESK_READS: readonly (readonly [key: string, path: string, query?: Record<string, string>])[] = [
  ["portfolio", "/portfolio"],
  ["brief", "/brief", { overlay: "off" }],
  ["nav-series", "/nav-series"],
  ["allocations", "/allocations"],
  ["performance", "/performance"],
];

const deskReads = createDeskCache<Awaited<ReturnType<typeof officialGet>>>();

/** House book from the official catalog routes. Stub and withheld reads stay empty. */
export function useOfficialDesk(): DeskInput {
  const [state, setState] = useState<DeskInput>(READING);

  useEffect(() => {
    let alive = true;
    void (async () => {
      const reads = await Promise.all(
        DESK_READS.map(([key, path, query]) => deskReads.load(key, () => officialGet(path, query))),
      );
      if (!alive) return;
      // A withheld or failed read is a transport outcome, not a dataset. Forget those keys so
      // the next mount tries again instead of replaying the failure until the window closes.
      const failedKeys = DESK_READS.filter((_, i) => !reads[i].ok).map(([key]) => key);
      for (const key of failedKeys) deskReads.invalidate(key);
      const failed = reads.find((read) => !read.ok);
      if (failed && !failed.ok) {
        setState({ ...READING, loading: false, error: failed.reason });
        return;
      }
      const [portfolio, brief, nav, allocations, performance] = reads;
      if (!portfolio.ok || !brief.ok || !nav.ok || !allocations.ok || !performance.ok) return;
      const book = houseBookFromPayloads({
        portfolio: portfolio.body,
        brief: brief.body,
        nav: nav.body,
        allocations: allocations.body,
        performance: performance.body,
      });
      if (!book) {
        setState({ ...READING, loading: false, error: "The official API withheld this read." });
        return;
      }
      setState({
        loading: false,
        configured: true,
        error: null,
        navContractError: null,
        positions: book.positions.map(toPosition),
        nav: toNav(book),
        metricsAsOf: book.asOf,
        kpis: kpisFrom(book),
      });
    })();
    return () => {
      alive = false;
    };
  }, []);

  return state;
}
