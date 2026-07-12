/**
 * Shared types for the digiquant.io live-price data layer (#1461/#1462).
 *
 * Two browser lanes feed these shapes (see digiquant/supabase/README.md):
 *   - crypto  → Coinbase's public keyless WS (per-product ticker stream)
 *   - equities → Supabase Realtime broadcast channel "prices:live"
 * with a daily-close SEED/fallback from the `public_price_latest` view so
 * values exist before the first tick and when a lane is dark.
 *
 * The two consumer lanes (StockTicker tape + Olympus live portfolio section)
 * build against these types — treat them as the contract.
 */

import type { SupabaseClient } from "@supabase/supabase-js";

/** Where a {@link LiveQuote} came from — for badging and staleness rules. */
export type LiveQuoteSource = "coinbase" | "broadcast" | "seed";

/**
 * One instrument's latest observed price.
 *
 * `stale` is the load-bearing flag: `true` means the value is only the daily
 * close seed (or a lane went dark) — NOT a live tick. Consumers that value or
 * badge "live" must gate on `!stale`, never on mere presence in the map.
 */
export interface LiveQuote {
  /** Uppercase ticker / Coinbase product_id — "SPY", "BTC-USD". */
  symbol: string;
  /** Last observed price. */
  price: number;
  /** Percent change (points): +1.24 means +1.24%. `0` when a source omits it. */
  changePct: number;
  /** Direction for the money colors: `changePct >= 0`. Binary — no neutral. */
  up: boolean;
  /** Epoch milliseconds of the observation. */
  ts: number;
  /** `true` = daily-close seed or dark lane; `false` = a real live tick. */
  stale: boolean;
  /** Provenance of this value. */
  source: LiveQuoteSource;
}

/** Symbol → latest quote. Keys are uppercase tickers / Coinbase product_ids. */
export type LivePriceMap = Record<string, LiveQuote>;

/** Options for {@link useLivePrices}. */
export interface UseLivePricesOptions {
  /**
   * Symbols to seed from `public_price_latest` and surface in the map
   * (equities AND crypto, uppercase — "SPY", "BTC-USD"). When non-empty it
   * also bounds the map: broadcast quotes outside this set (∪ cryptoProductIds)
   * are ignored. Empty/omitted = accept every broadcast symbol.
   */
  symbols?: string[];
  /**
   * Coinbase product_ids to stream live from the public WS, e.g.
   * `["BTC-USD","ETH-USD","SOL-USD"]`. Streams regardless of Supabase config —
   * this is the keyless lane and never touches the Supabase client.
   */
  cryptoProductIds?: string[];
  /**
   * Test seam / explicit override: the Supabase client to use for the seed
   * SELECT and the equity broadcast. Defaults to the module singleton (which is
   * `null` when the public env vars are unset). Pass `null` to force the
   * equity+seed lanes dark (crypto still streams).
   */
  client?: SupabaseClient | null;
}

/**
 * One position from `public_portfolio_positions`, enriched with the live mark.
 *
 * Column projection is the privacy allowlist (performance only — never
 * rationale / PM notes / thesis). `name`/`category`/`sector_bucket` are often
 * null in the view; `CASH` carries a null price and stays flat in valuation.
 */
export interface LivePosition {
  ticker: string;
  name: string | null;
  category: string | null;
  sectorBucket: string | null;
  weightPct: number;
  entryPrice: number | null;
  entryDate: string | null;
  /** Daily-close mark from the snapshot (`metrics_as_of`). */
  currentPrice: number | null;
  dayChangePct: number | null;
  unrealizedPnlPct: number | null;
  sinceEntryReturnPct: number | null;
  metricsAsOf: string | null;
  /** Live mark when a real (non-stale) quote exists, else `currentPrice`. */
  livePrice: number | null;
  /** `true` only when `livePrice` came from a live tick (`!quote.stale`). */
  isLive: boolean;
}

/** One point of the NAV series from `public_nav_history`. */
export interface NavPoint {
  date: string;
  nav: number;
  cashPct: number | null;
  investedPct: number | null;
  dayReturnPct: number | null;
}

/** Return shape of {@link useLivePortfolio}. */
export interface LivePortfolioResult {
  loading: boolean;
  error: string | null;
  /** `true` when a Supabase client exists (public env vars are set). */
  configured: boolean;
  /** The position book (latest snapshot date), each enriched with its mark. */
  positions: LivePosition[];
  /** NAV series, oldest → newest. */
  nav: NavPoint[];
  /** Latest NAV row value — the close-based anchor for the live total. */
  latestNav: number | null;
  /**
   * Book revalued at live prices, anchored on `latestNav`:
   * `latestNav * (1 + liveVsMarkPct/100)`. With no live ticks this equals the
   * published book value. `null` when `latestNav` is unknown.
   */
  liveTotalValue: number | null;
  /**
   * Dimensionless live move vs the snapshot marks (percent points):
   * `Σ weightᵢ · (livePriceᵢ / currentPriceᵢ − 1)`, live (non-stale) legs only.
   * `0` when nothing is live. Exposed separately so the UI can recompose the
   * total against a different NAV anchor if the dates ever diverge.
   */
  liveVsMarkPct: number;
  /** Snapshot date the marks/weights are as of. */
  metricsAsOf: string | null;
  /** Always `true` for this book — a research/paper portfolio, not a live fund. */
  isResearchPortfolio: boolean;
}

/** Options for {@link useLivePortfolio}. */
export interface UseLivePortfolioOptions {
  /**
   * Coinbase product_ids to stream live for any crypto legs. Defaults to the
   * book's own `-USD` tickers; today's macro book holds none, so this is
   * inert until the book adds crypto (or a caller overrides it).
   */
  cryptoProductIds?: string[];
  /**
   * Test seam / explicit override for the Supabase client. Defaults to the
   * module singleton (`null` when the public env vars are unset → the hook
   * returns an empty, non-configured result without crashing).
   */
  client?: SupabaseClient | null;
}
