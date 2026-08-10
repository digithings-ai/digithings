/**
 * Price chart — candlesticks and volume on TradingView Lightweight Charts:
 * candles in the `--up`/`--down` money colors, volume in the hairline token,
 * re-themed live on theme and livery flips. Consumes the shared <PriceChart/>
 * primitive from @digithings/web with its deterministic demo OHLC walk.
 * Static display template.
 */
import { PriceChart, PRICE_CHART_DEMO } from "@digithings/web";

export function PriceChartReference() {
  return <PriceChart candles={PRICE_CHART_DEMO.candles} volume={PRICE_CHART_DEMO.volume} />;
}
