"use client";

import { useEffect, useState } from "react";
import type { LivePerformanceKpis } from "@digithings/ui";
import { houseBookFromPayloads, officialGet, type OfficialHouseBook } from "@/lib/official-api";
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

/** House book from the official catalog routes. Stub and withheld reads stay empty. */
export function useOfficialDesk(): DeskInput {
  const [state, setState] = useState<DeskInput>(READING);

  useEffect(() => {
    let alive = true;
    void (async () => {
      const [portfolio, brief, nav, allocations, performance] = await Promise.all([
        officialGet("/portfolio"),
        officialGet("/brief", { overlay: "off" }),
        officialGet("/nav-series"),
        officialGet("/allocations"),
        officialGet("/performance"),
      ]);
      if (!alive) return;
      const reads = [portfolio, brief, nav, allocations, performance];
      const failed = reads.find((read) => !read.ok);
      if (failed && !failed.ok) {
        setState({ ...READING, loading: false, error: failed.reason });
        return;
      }
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
