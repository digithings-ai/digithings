import type { VelaWorkspaceOptions } from "@luxalgo/vela/workspace";
import { HOUSE_PROVIDER_NAME, HouseBarsProvider } from "./house-bars-provider";

/** Caption when the workspace fails to mount. The chart chrome stays. */
export const VELA_UNAVAILABLE = "LuxAlgo Vela · chart unavailable";

/**
 * House bars, by way of the `house:` provider prefix. The prefix is what stops
 * Vela resolving the symbol through a vendor feed — the desk registered Binance
 * and Coinbase here before (DIG-2814), so a bare ticker rendered Binance
 * BTCUSDT and fetched it from the browser.
 */
export const VELA_SYMBOL = `${HOUSE_PROVIDER_NAME}:BTC-USD`;
export const VELA_TIMEFRAME = "15";

/**
 * Vanilla LuxAlgo workspace. One chart, dark theme, house bars only.
 * Autoscale and the price window stay on Vela's defaults. The Vela watermark stays on.
 */
export function velaWorkspaceOptions(): VelaWorkspaceOptions {
  return {
    layout: false,
    symbol: VELA_SYMBOL,
    timeframe: VELA_TIMEFRAME,
    theme: "dark",
    providers: {
      house: () => new HouseBarsProvider(),
    },
  };
}
