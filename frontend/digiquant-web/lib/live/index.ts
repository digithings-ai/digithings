/**
 * Live-price data layer for digiquant.io (#1461/#1462) — the app-local wiring
 * that feeds the shared @digithings/web StockTicker + finance-tearsheet
 * surfaces. Import hooks/types from here.
 */
export { supabase, isSupabaseConfigured } from "./supabaseClient";
export { useLivePrices } from "./useLivePrices";
export { useLivePortfolio } from "./useLivePortfolio";
export {
  computeLiveTotal,
  coinbaseTickerToLive,
  broadcastQuoteToLive,
  seedRowToLive,
  applyQuotes,
  normalizeSymbols,
} from "./quote-transforms";
export type {
  LiveQuote,
  LiveQuoteSource,
  LivePriceMap,
  LivePosition,
  NavPoint,
  LivePortfolioResult,
  UseLivePricesOptions,
  UseLivePortfolioOptions,
} from "./types";
