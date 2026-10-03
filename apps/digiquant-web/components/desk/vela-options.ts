import type { DataProvider } from "@luxalgo/vela/providers/binance";
import type { VelaWorkspaceOptions } from "@luxalgo/vela/workspace";

/** Caption when the workspace fails to mount. The chart chrome stays. */
export const VELA_UNAVAILABLE = "LuxAlgo Vela · chart unavailable";

/** Binance spot BTC. A bare ticker would follow provider declaration order; the prefix pins the venue. */
export const VELA_SYMBOL = "binance:BTCUSDT";
export const VELA_TIMEFRAME = "15";

/**
 * Vanilla LuxAlgo workspace. One chart, dark theme, Binance then Coinbase.
 * Autoscale and the price window stay on Vela's defaults. The Vela watermark stays on.
 */
export function velaWorkspaceOptions(
  binance: new () => DataProvider,
  coinbase: new () => DataProvider,
): VelaWorkspaceOptions {
  return {
    layout: false,
    symbol: VELA_SYMBOL,
    timeframe: VELA_TIMEFRAME,
    theme: "dark",
    providers: {
      binance: () => new binance(),
      coinbase: () => new coinbase(),
    },
  };
}
