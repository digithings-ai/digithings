/** Strategies this site has a route for. Stats stay unpublished until the live store returns a tearsheet. */
export const PUBLISHED_STRATEGIES = [
  { id: "btc_slapper", label: "BTC L/S", symbol: "BTC-USD" },
  { id: "eth_slapper", label: "ETH L/S", symbol: "ETH-USD" },
  { id: "sol_slapper", label: "SOL L/S", symbol: "SOL-USD" },
  { id: "btc_sdca", label: "BTC-SDCA", symbol: "BTC-USD" },
] as const;

export type PublishedStrategyId = (typeof PUBLISHED_STRATEGIES)[number]["id"];
