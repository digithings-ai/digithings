/** User-facing strategy titles — internal slugs (e.g. btc_slapper) stay in URLs only. */

const DISPLAY_NAMES: Record<string, string> = {
  btc_slapper: "BTC long/short",
  eth_slapper: "ETH long/short",
  sol_slapper: "SOL long/short",
};

/** Resolve a human label; prefers index.json `label`, then the canonical map. */
export function strategyDisplayName(slug: string, label?: string): string {
  if (label && !/slapper/i.test(label)) return label;
  return DISPLAY_NAMES[slug] ?? slug.replace(/_/g, " ");
}

/** Base asset from a tearsheet symbol (e.g. BTC-USD → BTC). */
export function symbolBase(symbol: string): string {
  return symbol.split("-")[0] ?? symbol;
}
