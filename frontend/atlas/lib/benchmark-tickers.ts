/**
 * ETFs used for Performance page comparison charts. Must stay in sync with
 * `BENCHMARKS` in scripts/update_tearsheet.py and populated in price_history
 * (e.g. scripts/preload-history.py --supabase).
 *
 * IBIT: BTC spot ETF proxy. EEM: emerging markets. IWM: small-cap.
 */
export const DASHBOARD_BENCHMARK_TICKERS = [
  'SPY',
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
