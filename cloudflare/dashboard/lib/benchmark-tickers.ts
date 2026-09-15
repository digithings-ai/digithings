/**
 * ETFs used for Performance page comparison charts. Must stay in sync with
 * `BENCHMARKS` in scripts/update_tearsheet.py; closes come from the R2 market
 * API (`fetchMarketCloses`) — the Supabase `price_history` table this list was
 * once populated into was dropped in migration 127 (#4053).
 *
 * IBIT: BTC spot ETF proxy. EEM: emerging markets. IWM: small-cap.
 */
/** Default relative-performance benchmark for Brief + digiquant landing + tearsheet. */
export const DEFAULT_BRIEF_BENCHMARK_TICKER = 'SPY';

export const DASHBOARD_BENCHMARK_TICKERS = [
  DEFAULT_BRIEF_BENCHMARK_TICKER,
  'QQQ',
  'DIA',
  'IWM',
  'VTI',
  'EEM',
  'TLT',
  'IEF',
  'AGG',
  'HYG',
  'GLD',
  'SLV',
  'USO',
  'UUP',
  'IBIT',
  'BITO',
  'EFA',
] as const;

/** Prefer SPY (Performance / digiquant SSOT); else first dashboard ticker with history. */
export function pickBriefBenchmarkTicker(
  benchmarks: Record<string, { history?: readonly unknown[] | null } | undefined>
): string | null {
  if (benchmarks[DEFAULT_BRIEF_BENCHMARK_TICKER]?.history?.length) {
    return DEFAULT_BRIEF_BENCHMARK_TICKER;
  }
  for (const t of DASHBOARD_BENCHMARK_TICKERS) {
    if (benchmarks[t]?.history?.length) return t;
  }
  return null;
}

/** Shown first in comparable picker (major ETFs / names users expect). */
export const PRIORITY_COMPARABLE_TICKERS: string[] = [
  'SPY',
  'QQQ',
  'IWM',
  'EEM',
  'VOO',
  'VTI',
  'DIA',
  'GLD',
  'TLT',
  'IBIT',
  'BITO',
  'XLE',
  'XLF',
  'XLK',
  'ACWI',
  'EFA',
  'AGG',
  'MSFT',
  'AAPL',
  'GOOGL',
  'NVDA',
];

/** Sort universe: priority tickers first (if present), then A–Z. */
export function sortTickerUniverse(tickers: string[]): string[] {
  const upper = tickers.map((t) => String(t).toUpperCase().trim()).filter(Boolean);
  const set = new Set(upper);
  const priority = PRIORITY_COMPARABLE_TICKERS.filter((t) => set.has(t));
  const rest = [...set].filter((t) => !PRIORITY_COMPARABLE_TICKERS.includes(t)).sort();
  return [...priority, ...rest];
}
