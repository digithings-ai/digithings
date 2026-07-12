"use client";

/* eslint-disable react-hooks/set-state-in-effect -- async fetch lifecycle (mirrors olympus lib/hooks/use-async-data.ts) */

/**
 * useLivePortfolio (#1461/#1462) — reads the public portfolio book +
 * NAV series once, then values it live via {@link useLivePrices}.
 *
 *   - `public_portfolio_positions` — latest-date book (privacy-allowlisted:
 *     performance only, never rationale / PM notes / thesis).
 *   - `public_nav_history` — NAV + cash/invested % + daily return series.
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
  computeLiveTotal,
  navRowToPoint,
  positionRowToLive,
  type PositionRow,
} from "./quote-transforms";

const POSITION_COLUMNS =
  "ticker, name, category, sector_bucket, weight_pct, entry_price, entry_date, current_price, day_change_pct, unrealized_pnl_pct, since_entry_return_pct, metrics_as_of";
const NAV_COLUMNS = "date, nav, cash_pct, invested_pct, day_return_pct";

export function useLivePortfolio(options: UseLivePortfolioOptions = {}): LivePortfolioResult {
  const client = "client" in options ? options.client ?? null : supabase;
  const configured = Boolean(client);

  const [rawPositions, setRawPositions] = useState<PositionRow[]>([]);
  const [nav, setNav] = useState<NavPoint[]>([]);
  const [loading, setLoading] = useState<boolean>(configured);
  const [error, setError] = useState<string | null>(null);

  // One-shot read of the book + NAV series. No client → `loading` stays at its
  // initial `false` (see useState above); nothing to fetch.
  useEffect(() => {
    if (!client) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    void (async () => {
      try {
        const [posRes, navRes] = await Promise.all([
          client.from("public_portfolio_positions").select(POSITION_COLUMNS),
          client.from("public_nav_history").select(NAV_COLUMNS).order("date", { ascending: true }),
        ]);
        if (cancelled) return;
        if (posRes.error) throw new Error(posRes.error.message);
        if (navRes.error) throw new Error(navRes.error.message);
        setRawPositions(Array.isArray(posRes.data) ? (posRes.data as PositionRow[]) : []);
        setNav(
          (Array.isArray(navRes.data) ? navRes.data : [])
            .map((r) => navRowToPoint(r as Record<string, unknown>))
            .filter((p): p is NavPoint => p !== null),
        );
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

  return {
    loading,
    error,
    configured,
    positions,
    nav,
    latestNav,
    liveTotalValue,
    liveVsMarkPct,
    metricsAsOf,
    isResearchPortfolio: true,
  };
}
