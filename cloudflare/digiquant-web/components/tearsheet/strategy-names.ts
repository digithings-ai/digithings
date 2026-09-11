/** User-facing strategy titles — internal slugs (e.g. btc_slapper) stay in URLs only. */

const DISPLAY_NAMES: Record<string, string> = {
  btc_slapper: "BTC L/S",
  eth_slapper: "ETH L/S",
  sol_slapper: "SOL L/S",
  btc_sdca: "BTC-SDCA",
};

/** Resolve a human label; canonical map wins so a stale store label cannot lie. */
export function strategyDisplayName(slug: string, label?: string): string {
  if (DISPLAY_NAMES[slug]) return DISPLAY_NAMES[slug];
  if (label && !/slapper/i.test(label)) return label;
  return slug.replace(/_/g, " ");
}

/** Base asset from a tearsheet symbol (e.g. BTC-USD → BTC). */
export function symbolBase(symbol: string): string {
  return symbol.split("-")[0] ?? symbol;
}
