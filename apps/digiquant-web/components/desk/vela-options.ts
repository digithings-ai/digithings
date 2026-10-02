/** LuxAlgo Vela on the charts page. Coinbase products only. No invented prices. */

export const VELA_UNAVAILABLE = "LuxAlgo Vela · chart unavailable";
export const VELA_FADE_MS = 700;
export const VELA_FEED_MAX_MS = 10_000;
export const VELA_PRODUCTS = ["BTC-USD", "ETH-USD", "SOL-USD"] as const;
export type VelaProduct = (typeof VELA_PRODUCTS)[number];

/** Caption once the Coinbase series, volume, and the three studies are on the pane. */
export function velaReadyCaption(product: VelaProduct): string {
  return `LuxAlgo Vela · ${product} · 1m · volume · SMA 20 · EMA 50 · Bollinger`;
}

/** Opacity stays 0 until the canvas has painted, then fades. Reduced motion is immediate. */
export function velaHostStyle(reduced: boolean, painted: boolean): { opacity: "0" | "1"; transition: string } {
  if (reduced) return { opacity: "1", transition: "none" };
  return { opacity: painted ? "1" : "0", transition: `opacity ${VELA_FADE_MS}ms ease` };
}

/** Public Vela options. Autoscale stays off. The only feed prefix is Coinbase. */
export function velaChartOptions(product: VelaProduct, reduced: boolean) {
  return {
    symbol: `coinbase:${product}`,
    timeframe: "1" as const,
    bars: 300,
    live: !reduced,
    volume: true,
    drawings: false as const,
    animations: reduced ? (false as const) : { intro: false, zoom: true, pan: true, autoscale: false as const },
  };
}
