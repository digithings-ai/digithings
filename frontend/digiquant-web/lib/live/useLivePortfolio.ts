"use client";

/* eslint-disable react-hooks/set-state-in-effect -- async fetch lifecycle (mirrors dashboard lib/hooks/use-async-data.ts) */

/**
 * useLivePortfolio (#1461/#1462) — reads the public portfolio book +
 * NAV series once, then values it live via {@link useLivePrices}.
 *
 *   - `public_portfolio_positions` — latest-date book (privacy-allowlisted:
 *     performance only, never rationale / PM notes / thesis).
 *   - `public_accounting_nav_history` — curated NAV (#2599): finalized accounting
 *     tips preferred; dates without a final tip use labeled legacy nav_history
 *     (`source=legacy_nav_history`). This view is the contracted public series —
 *     readers fail closed when it is missing (apply migrations 072–074). Do not
 *     silently re-point to `public_nav_history` in the browser.
 *
 * Live valuation uses a symbol's quote ONLY when it is a real (non-stale) tick;
 * otherwise the leg falls back to `current_price` and stays flat. With no live
 * ticks (dormant feed / market closed) `liveTotalValue` equals the published
 * `latestNav`. CASH and any priceless leg contribute flat.
 *
 * Null-client safe: returns an empty, `configured:false` result (the static
 * build path) with no crash. This book is always a research/paper portfolio —
 * `isResearchPortfolio` is `true` so the UI can badge it and nobody mistakes it
 * for a live-traded fund.
 */
import { useEffect, useMemo, useState } from "react";
import { supabase } from "./supabaseClient";
import { useLivePrices } from "./useLivePrices";
import type { LivePortfolioResult, NavPoint, UseLivePortfolioOptions } from "./types";
import {
  computeLivePerformanceKpis,
  type LivePerformanceKpis,
} from "@digithings/web";
import {
  computeLiveTotal,
  navRowToPoint,
  positionRowToLive,
  type PositionRow,
} from "./quote-transforms";
import {
  ACCOUNTING_NAV_VIEW,
  AccountingNavContractError,
} from "./accounting-nav-contract";

const POSITION_COLUMNS =
  "ticker, name, category, sector_bucket, weight_pct, entry_price, entry_date, current_price, day_change_pct, unrealized_pnl_pct, since_entry_return_pct, metrics_as_of";
const NAV_COLUMNS = "date, nav, cash_pct, invested_pct, day_return_pct, source, contract";
const LANDING_BENCHMARK_TICKER = "SPY";

export function useLivePortfolio(options: UseLivePortfolioOptions = {}): LivePortfolioResult {
  const client = "client" in options ? options.client ?? null : supabase;
  const configured = Boolean(client);

  const [rawPositions, setRawPositions] = useState<PositionRow[]>([]);
  const [nav, setNav] = useState<NavPoint[]>([]);
  const [benchmarkHistory, setBenchmarkHistory] = useState<Array<{ date: string; price: number }>>(
    [],
  );
  const [loading, setLoading] = useState<boolean>(configured);
  const [error, setError] = useState<string | null>(null);
  const [navContractError, setNavContractError] = useState<string | null>(null);

  // One-shot read of the book + NAV series. No client → `loading` stays at its
  // initial `false` (see useState above); nothing to fetch.
  useEffect(() => {
    if (!client) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setNavContractError(null);
    void (async () => {
      try {
        const posRes = await client.from("public_portfolio_positions").select(POSITION_COLUMNS);
        if (cancelled) return;
        if (posRes.error) throw new Error(posRes.error.message);
        setRawPositions(Array.isArray(posRes.data) ? (posRes.data as PositionRow[]) : []);

        const navRes = await client
          .from(ACCOUNTING_NAV_VIEW)
          .select(NAV_COLUMNS)
          .order("date", { ascending: true });
        if (cancelled) return;
        if (navRes.error) {
          const contractErr = new AccountingNavContractError(navRes.error);
          setNavContractError(contractErr.message);
          setNav([]);
          setBenchmarkHistory([]);
        } else {
          const navPoints = (Array.isArray(navRes.data) ? navRes.data : [])
            .map((r) => navRowToPoint(r as Record<string, unknown>))
            .filter((p): p is NavPoint => p !== null);
          setNav(navPoints);

          const firstDate = navPoints[0]?.date;
          if (firstDate) {
            const benchRes = await client
              .from("price_history")
              .select("date, close")
              .eq("ticker", LANDING_BENCHMARK_TICKER)
              .gte("date", firstDate)
              .order("date", { ascending: true });
            if (!cancelled && !benchRes.error && Array.isArray(benchRes.data)) {
              setBenchmarkHistory(
                benchRes.data
                  .map((r) => {
                    const date = typeof r.date === "string" ? r.date : null;
                    const price = typeof r.close === "number" ? r.close : Number(r.close);
                    return date && Number.isFinite(price) ? { date, price } : null;
                  })
                  .filter((p): p is { date: string; price: number } => p !== null),
              );
            } else if (!cancelled) {
              setBenchmarkHistory([]);
            }
          } else {
            setBenchmarkHistory([]);
          }
        }
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Failed to load portfolio");
          setRawPositions([]);
          setNav([]);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [client]);

  // Symbols to price live (ex-CASH); crypto legs stream from Coinbase.
  const symbols = useMemo(
    () =>
      rawPositions
        .map((r) => (typeof r.ticker === "string" ? r.ticker.trim().toUpperCase() : ""))
        .filter((t) => t && t !== "CASH"),
    [rawPositions],
  );
  const derivedCrypto = useMemo(() => symbols.filter((s) => s.endsWith("-USD")), [symbols]);
  const cryptoProductIds = options.cryptoProductIds ?? derivedCrypto;

  const quotes = useLivePrices({ symbols, cryptoProductIds, client });

  const positions = useMemo(
    () => rawPositions.map((r) => positionRowToLive(r, quotes)),
    [rawPositions, quotes],
  );
  const latestNav = nav.length > 0 ? nav[nav.length - 1].nav : null;
  const { liveVsMarkPct, liveTotalValue } = useMemo(
    () => computeLiveTotal(positions, quotes, latestNav),
    [positions, quotes, latestNav],
  );
  const metricsAsOf = useMemo(
    () => positions.find((p) => p.metricsAsOf)?.metricsAsOf ?? null,
    [positions],
  );

  const kpis: LivePerformanceKpis | null = useMemo(() => {
    if (nav.length === 0) return null;
    const kpiPositions = positions.map((p) => {
      const q = quotes[p.ticker];
      const livePriceDate =
        p.isLive && q?.ts
          ? new Date(q.ts).toISOString().slice(0, 10)
          : null;
      return {
        ticker: p.ticker,
        weightPct: p.weightPct,
        markPrice: p.currentPrice,
        effectivePrice: p.livePrice,
        isLive: p.isLive,
        metricsAsOf: p.metricsAsOf,
        livePriceDate,
      };
    });
    return computeLivePerformanceKpis({
      positions: kpiPositions,
      navHistory: nav.map((n) => ({ date: n.date, nav: n.nav })),
      benchmarkHistory,
      benchmarkTicker: benchmarkHistory.length ? LANDING_BENCHMARK_TICKER : null,
    });
  }, [positions, quotes, nav, benchmarkHistory]);

  return {
    loading,
    error,
    navContractError,
    configured,
    positions,
    nav,
    latestNav,
    liveTotalValue: kpis?.liveNav ?? liveTotalValue,
    liveVsMarkPct: kpis?.liveVsMarkPct ?? liveVsMarkPct,
    metricsAsOf: kpis?.priceAsOfDate ?? metricsAsOf,
    kpis,
    isResearchPortfolio: true,
  };
}
